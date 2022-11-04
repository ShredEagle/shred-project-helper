import ast
import asyncio
import typing
import re
import pdb
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from colorama import Fore, Style
import yaml
import click
from git.repo import Repo
from github import Repository
from halo import Halo

from sph.utils import extract_info_from_conan_ref, t
from sph.conan_ref import ConanRefDescriptor

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
            if dep_name != editable.ref.name:
                if dep_name in [x.ref.name for x in editables]:
                    dep_editable = next(x for x in editables if x.ref.name == dep_name)
                    if dep_editable is not None:
                        editable.required_local_lib.append(ConanRefDescriptor(dep))
                else:
                    editable.required_external_lib.append(
                        ConanRefDescriptor(dep)
                    )


def create_editable_from_workspace(workspace, github_client=None):
    editable_list = []

    for conan_ref, project_conan_path in workspace.local_refs:
        if project_conan_path.exists():
            conan_ref.is_local = True
            editable_list.append(Editable(conan_ref, project_conan_path, github_client))
        else:
            conan_ref.is_local = False

    for ed in editable_list:
        create_editable_dependency(ed, editable_list)

    return editable_list

class Editable:
    ref: ConanRefDescriptor
    conan_path: Path
    required_local_lib: list[ConanRefDescriptor]
    required_external_lib: list[ConanRefDescriptor]
    repo: Repo
    gh_repo: Repository

    def __init__(self, conan_ref, conan_path, gh_client):
        self.ref = conan_ref
        self.conan_path = conan_path / "conanfile.py"
        self.repo = Repo(self.conan_path.parents[1].resolve())
        self.required_external_lib = []
        self.required_local_lib = []
        self.gh_repo_name = None
        self.gh_repo = None
        self.future = None
        self.current_run = None

        remote_url = list(self.repo.remote("origin").urls)[0]
        match = re.search(r"github.com:(.*)/(.*(?=\.g)|.*)", remote_url)

        if match and gh_client:
            self.org = match.group(1)
            self.gh_repo_name = match.group(2)
            self.gh_client = gh_client

    def setup_gh_repo_task(self):
        if self.gh_repo:
            return True

        try:
            self.gh_repo = self.gh_client.get_repo(f"{self.org}/{self.gh_repo_name}")
            return True
        except Exception:
            return False
        
    def setup_gh_repo(self, callback):
        if self.gh_repo_name:
            exe = ThreadPoolExecutor(max_workers=1)
            f = exe.submit(self.setup_gh_repo_task)
            f.add_done_callback(callback)

    def __str__(self, level=0):
        local_lib_str = "\n"
        for lib in self.required_local_lib:
            local_lib_str += lib.__str__(level + 1)
        ext_lib_str = "\n"
        for lib in self.required_external_lib:
            ext_lib_str += lib.__str__(level + 2)

        return f"{t(level)}{self.ref.conan_ref}:\n" + f"{t(level)}Local dependencies:{local_lib_str}{t(level)}" + f"External dependencies:{ext_lib_str}"
    
    def get_dependency_from_name(self, name):
       return next(filter(lambda x: x.name == name, self.required_external_lib + self.required_local_lib))

    def checking_workflow_task(self, force=False):
        if self.current_run and not force:
            return self.current_run

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

            if self.current_run:
                return self.current_run
            else:
                return None
        except Exception:
            return None

    def check_workflow(self, callback):
        if self.gh_repo_name:
            exe = ThreadPoolExecutor(max_workers=1)
            f = exe.submit(self.checking_workflow_task)
            f.add_done_callback(callback)


def get_editable_status(editable, dependency_graph):
    pass
