import ast
import re

from git import GitCommandError
from git.repo import Repo

from sph.conan_package import ConanPackage
from sph.semver import Semver


class Editable:
    def __init__(self, conan_path):
        # FIX: This assume the name of the conanfile
        self.conan_path = (
            conan_path / "conanfile.py"
            if "conanfile.py" not in str(conan_path)
            else conan_path
        ).resolve()
        self.is_in_filesystem = self.conan_path.exists()

        if self.is_in_filesystem:
            # FIX: This assume the position of the git repository
            self.repo = Repo(self.conan_path.parents[1].resolve())
            self.required_conan_ref = []

            with open(self.conan_path, "r") as conanfile:
                conanfile_ast = ast.parse(conanfile.read())
                for node in ast.iter_child_nodes(conanfile_ast):
                    if isinstance(node, ast.ClassDef):
                        for class_node in ast.iter_child_nodes(node):
                            if isinstance(class_node, ast.Assign):
                                for target in class_node.targets:
                                    if target.id == "name":
                                        self.package = ConanPackage(
                                            class_node.value.value, self
                                        )

            self.last_workflow_call = None
            self.succesful_develop_runs = []
            self.checking_for_workflow = False
            self.cmake_status = None
            self.rev_list = None
            self.is_repo_dirty = None
            self.conan_base_version = None
            self.workflows_version = None

            self.github_org = None
            self.github_repo = None
            self.active_sha_run = None

            remote_url = list(self.repo.remote("origin").urls)[0]
            match = re.search(r"github.com:(.*)/(.*(?=\.g)|.*)", remote_url)

            if match:
                self.github_owner = match.group(1)
                self.github_repo = match.group(2)

    def update_conan_base_version(self):
        conan_base_regex = r"python_requires=.*\/(\d+\.\d+\.\d+)@"
        if self.is_local:
            with open(self.conan_path.resolve(), "r") as conan_file:
                for line in conan_file.readlines():
                    match = re.search(conan_base_regex, line)
                    if match:
                        self.conan_base_version = Semver(match.group(1))

    def update_rev_list(self, future):
        if (self.repo.active_branch.tracking_branch()):
            rev_list_regex = r"(\d)\t(\d)"
            rev_list = self.repo.git.rev_list(
                [
                    "--left-right",
                    "--count",
                    f"{self.repo.active_branch}...{self.repo.active_branch.tracking_branch()}",
                ]
            )
            self.rev_list = re.search(rev_list_regex, rev_list)

        if not future.cancelled():
            future.set_result(True)

    def check_repo_dirty(self, future):
        try:
            # if repo was dirty and is now clean we need to empty
            # the status of active_sha_run
            if self.is_repo_dirty and not self.repo.is_dirty():
                self.active_sha_run = None
            self.is_repo_dirty = self.repo.is_dirty()
        except Exception:
            if not future.cancelled():
                future.set_result(False)

        if not future.cancelled():
            future.set_result(True)

    def check_cmake_submodule(self, future):
        # This needs git config --global status.submoduleSummary true
        cmake_match = None
        cmake_submodule_regex = r"cmake (\w+)\.\.\.(\w+) \((\d+)\)"
        try:
            if self.repo.git.config(["--global", "status.submoduleSummary"]) == "true":
                status = self.repo.git.status()
                for status_line in status.splitlines():
                    if status_line.startswith("* cmake"):
                        cmake_match = re.search(cmake_submodule_regex, status_line)
                        if cmake_match:
                            self.cmake_status = [
                                (" ", "fail"),
                                f"CMake submodule is {cmake_match.group(3)} commit behind",
                            ]
                if cmake_match is None:
                    self.cmake_status = [
                        (" ", "success"),
                        f"CMake submodule is up to date",
                    ]
            else:
                self.cmake_status = [
                    ("", "refname"),
                    " Can't check cmake submodule health please use git config --global status.submoduleSummary true",
                ]
        except GitCommandError:
            self.cmake_status = [
                ("", "refname"),
                " Can't check cmake submodule health please use git config --global status.submoduleSummary true",
            ]

        if not future.cancelled():
            future.set_result(True)

    def change_version(self, new_dependency, old_dependency=None):
        text = None
        newtext = None
        regex = r""
        if old_dependency is None:
            # matches a conan string reference of new_dependency
            # but does not match new_dependency/conan
            regex = r"{}\/(?!conan)[\w\.]+(@[\w]+\/[\w]+(#[\w])?)?".format(
                re.escape(new_dependency.package.name)
            )
        else:
            regex = re.escape(old_dependency)

        with open(self.conan_path, "r", newline="") as conanfile:
            text = conanfile.read()
            newtext = re.sub(regex, new_dependency.ref, text)
        with open(self.conan_path, "w", newline="") as resolvedfile:
            resolvedfile.write(newtext)

        if newtext != text:
            for dep in self.required_conan_ref:
                if dep.package.name == new_dependency.package.name:
                    dep.version = new_dependency.version
                    dep.user = new_dependency.user
                    dep.channel = new_dependency.channel
                    dep.revision = new_dependency.revision

            return True

        return False

    def get_dependency_from_package(self, package):
        return next(
            filter(
                lambda x: x.package == package,
                self.required_conan_ref,
            )
        )
