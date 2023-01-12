import ast
import re
from git.repo import Repo
from ratelimit import limits

from sph.conan_ref import ConanRef
from sph.semver import Semver

class GithubRunStub:
    def __init__(self, status, conclusion, head_sha):
        self.status = status
        self.conclusion = conclusion
        self.head_sha = head_sha

def create_editable_dependency(editable, editables):
    all_required_lib = []
    with open(editable.conan_path, "r") as conanfile:
        conanfile_ast = ast.parse(conanfile.read())
        for node in ast.iter_child_nodes(conanfile_ast):
            if isinstance(node, ast.ClassDef):
                for class_node in ast.iter_child_nodes(node):
                    if isinstance(class_node, ast.Assign):
                        for target in class_node.targets:
                            if target.id == "requires":
                                all_required_lib += [
                                    elt.value for elt in class_node.value.elts
                                ]

        for dep in all_required_lib:
            dep_name = dep.split("/")[0]
            if dep_name != editable.package.name:
                if dep_name in [x.package.name for x in editables]:
                    dep_editable = next(x for x in editables if x.package.name == dep_name)
                    if dep_editable is not None:
                        editable.required_local_lib.append(ConanRef(dep))
                else:
                    editable.required_external_lib.append(
                        ConanRef(dep)
                    )


def create_editable_from_workspace_list(workspaces, github_client=None, thread_pool=None):
    editable_list = []
    package_set = set()

    local_refs = set()
    for ws in workspaces:
        local_refs.update(ws.local_refs)

    for conan_ref, project_conan_path in local_refs:
        if project_conan_path.exists() and conan_ref.package not in package_set:
            conan_ref.has_local_editable = True
            package_set.add(conan_ref.package)
            editable_list.append(Editable(conan_ref.package, project_conan_path, github_client, thread_pool))
        else:
            conan_ref.has_local_editable = False

    for ed in editable_list:
        create_editable_dependency(ed, editable_list)

    return editable_list

class Editable:
    def __init__(self, conan_package, conan_path, gh_client, thread_pool):
        self.thread_pool = thread_pool
        self.package = conan_package
        # FIX: This assume the name of the conanfile
        self.conan_path = (conan_path / "conanfile.py" if "conanfile.py" not in str(conan_path) else conan_path).resolve()
        self.is_local = self.conan_path.exists()
        if self.is_local:
            # FIX: This assume the position of the git repository
            self.repo = Repo(self.conan_path.parents[1].resolve())
            self.required_external_lib = []
            self.required_local_lib = []

        self.gh_repo_name = None
        self.gh_repo = None
        self.current_run = None
        self.runs_develop = []
        self.checking_for_workflow = False
        self.cmake_status = None
        self.rev_list = None
        self.is_repo_dirty = None
        self.conan_base_version = None
        self.workflows_version = None

        remote_url = list(self.repo.remote("origin").urls)[0]
        match = re.search(r"github.com:(.*)/(.*(?=\.g)|.*)", remote_url)

        if match and gh_client:
            self.org = match.group(1)
            self.gh_repo_name = match.group(2)
            self.gh_client = gh_client

        self.setup_gh_repo()

    @limits(calls=1, period=0.5, raise_on_limit=False)
    def update_conan_base_version(self):
        conan_base_regex = r"python_requires=.*\/(\d+\.\d+\.\d+)@"
        if self.is_local:
            with open(self.conan_path.resolve(), "r") as conan_file:
                for line in conan_file.readlines():
                    match = re.search(conan_base_regex, line)
                    if match:
                        self.conan_base_version = Semver(match.group(1))
        pass

    @limits(calls=1, period=0.5, raise_on_limit=False)
    def update_rev_list(self):
        rev_list_regex = r"(\d)\t(\d)"
        rev_list = self.repo.git.rev_list(["--left-right", "--count", f"{self.repo.active_branch}...origin/develop"])
        self.rev_list = re.search(rev_list_regex, rev_list)

    @limits(calls=1, period=0.5, raise_on_limit=False)
    def check_repo_dirty(self):
        self.is_repo_dirty = self.repo.is_dirty()

    @limits(calls=1, period=0.5, raise_on_limit=False)
    def check_external_status(self):
        # This needs git config --global status.submoduleSummary true
        cmake_match = None
        cmake_submodule_regex = r"cmake (\w+)\.\.\.(\w+) \((\d+)\)"
        if self.repo.git.config(["--global", "status.submoduleSummary"]) == "true":
            status = self.repo.git.status()
            for status_line in status.splitlines():
                if status_line.startswith("* cmake"):
                    cmake_match = re.search(cmake_submodule_regex, status_line)
                    if cmake_match:
                        self.cmake_status = [(" ", "fail"), f"CMake submodule is {cmake_match.group(3)} commit behind"]
            if cmake_match is None:
                    self.cmake_status = [(" ", "success"), f"CMake submodule is up to date"]
        else:
            self.cmake_status = [("", "refname"), " Can't check cmake submodule health please use git config --global status.submoduleSummary true"]

    def change_version(self, new_dependency, old_dependency=None):
        text = None
        newtext = None
        regex = r''
        if old_dependency is None:
            # matches a conan string reference of new_dependency
            # but does not match new_dependency/conan
            regex = r"{}\/(?!conan)[\w\.]+(@[\w]+\/[\w]+(#[\w])?)?".format(re.escape(new_dependency.package.name))
        else:
            regex = re.escape(old_dependency)

        with open(self.conan_path, "r", newline="") as conanfile:
            text = conanfile.read()
            newtext = re.sub(regex, new_dependency.ref, text)
        with open(self.conan_path, "w") as resolvedfile:
            resolvedfile.write(newtext)

        if newtext != text:
            for dep in self.required_local_lib:
                if dep.package.name == new_dependency.package.name:
                    dep.version = new_dependency.version
                    dep.user = new_dependency.user
                    dep.channel = new_dependency.channel
                    dep.revision = new_dependency.revision

            for dep in self.required_external_lib:
                if dep.package.name == new_dependency.package.name:
                    dep.version = new_dependency.version
                    dep.user = new_dependency.user
                    dep.channel = new_dependency.channel
                    dep.revision = new_dependency.revision

            return True

        return False

    def setup_gh_repo_task(self):
        if self.gh_repo:
            return True

        try:
            self.gh_repo = self.gh_client.get_repo(f"{self.org}/{self.gh_repo_name}")
            return True
        except Exception:
            self.gh_repo = False
            return False
        
    def setup_gh_repo(self):
        if self.gh_repo_name and self.thread_pool:
            f = self.thread_pool.submit(self.setup_gh_repo_task)
            f.add_done_callback(self.check_workflow_cb)
        else:
            self.setup_gh_repo_task()
    
    def get_dependency_from_package(self, package):
       return next(filter(lambda x: x.package == package, self.required_external_lib + self.required_local_lib))

    def checking_workflow_task(self, force=False):
        if self.current_run and not force:
            return self.current_run

        self.checking_for_workflow = True
        self.current_run = None

        try:
            runs_queued = self.gh_repo.get_workflow_runs(
                branch=self.repo.active_branch.name, status='queued'
            )
            runs_in_progress = self.gh_repo.get_workflow_runs(
                branch=self.repo.active_branch.name, status='in_progress'
            )
            runs_completed = self.gh_repo.get_workflow_runs(
                branch=self.repo.active_branch.name, status='completed'
            )
            # FIX: should be able to configure develop name branch
            runs_develop = self.gh_repo.get_workflow_runs(
                branch="develop", status="completed"
            )
            if (
                runs_queued.totalCount > 0
                or runs_in_progress.totalCount > 0 or runs_completed.totalCount > 0
            ):
                for run in (
                        list(runs_queued)
                        + list(runs_in_progress) + list(runs_completed)
                ):
                    if run.head_sha == self.repo.head.commit.hexsha:
                        self.current_run = run

            for run in runs_develop[0:10]:
                self.runs_develop.append(GithubRunStub(
                    run.status,
                    run.conclusion,
                    run.head_sha))

            self.checking_for_workflow = False

        except Exception:
            self.checking_for_workflow = False
            self.current_run = None

    def check_workflow_wrapper(self, force=False):
        def wrapped():
            self.checking_workflow_task(force)
        return wrapped

    def check_workflow_cb(self, _):
        self.check_workflow(False)

    def check_workflow(self, force):
        if self.gh_repo and not self.checking_for_workflow:
            self.thread_pool.submit(self.check_workflow_wrapper(force))
