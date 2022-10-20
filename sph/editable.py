import ast
import typing
import re
from dataclasses import dataclass
from pathlib import Path

from colorama import Fore, Style
import yaml
import click
from git import Repo
from github import Repository
from halo import Halo

from sph.utils import extract_info_from_conan_ref

def t(level):
    return "  " * level

Editable = typing.NewType('Editable', None)

ExternalLib = typing.NewType("ExternalLib", None)

@dataclass
class ConanRefDescriptor:
    conan_ref: str
    name: str
    version: str
    user: str
    channel: str
    revision: str
    conflicts: [str]

    def __init__(self, ref):
        name, version, user, channel, revision = extract_info_from_conan_ref(
                ref
            )
        self.conan_ref = ref
        self.name = name
        self.version = version
        self.user = user
        self.channel = channel
        self.revision = revision
        self.conflicts = []

    def __eq__(self, other):
        self.conan_ref = other.conan_ref

    def __str__(self, level=0):
        return f'''{t(level)}{self.conan_ref}:
{t(level + 1)}name: {self.name}
{t(level + 1)}version: {self.version}
{t(level + 1)}user: {self.user}
{t(level + 1)}channel: {self.channel}
{t(level + 1)}revision: {self.revision}
{t(level + 1)}conflicts: {self.conflicts}
'''

    def print_check(self, level=0):
        if len(self.conflicts) > 0:
            ret = f"{t(level)}{self.conan_ref} conflicts with "
            for c in self.conflicts:
                for name in c:
                    ret += f"{Fore.RED}{name}{Fore.RESET} "
            Halo(ret).fail()
        else:
            ret = f"{t(level)}{self.conan_ref} is ok"
            Halo(ret).succeed()

@dataclass
class Editable:
    ref: ConanRefDescriptor
    conan_path: Path
    required_local_lib: [ConanRefDescriptor]
    required_external_lib: [ConanRefDescriptor]
    repo: Repo
    gh_repo_client: Repository

    def __str__(self, level=0):
        local_lib_str = "\n"
        for lib in self.required_local_lib:
            local_lib_str += lib.__str__(level + 1)
        ext_lib_str = "\n"
        for lib in self.required_external_lib:
            ext_lib_str += lib.__str__(level + 2)

        return f"{t(level)}{self.ref.conan_ref}:\n" + f"{t(level)}Local dependencies:{local_lib_str}{t(level)}" + f"External dependencies:{ext_lib_str}"

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

    loading_editables_spinner = Halo(text="Retrieving editables", spinner="dots")
    loading_editables_spinner.start()

    editables = []

    for conan_ref, project_conan_path in workspace.editables:
        repo = Repo(project_conan_path.parents[0].resolve())
        remote_url = list(repo.remote("origin").urls)[0]
        match = re.search(r"github.com:(.*)/([^.]*)(\.git)?", remote_url)

        if match and github_client:
            org = match.group(1)
            gh_repo = match.group(2)
        elif github_client:
            click.echo()
            click.echo(f"There is no github repository for {name}")
            raise click.Abort()

        editable = Editable(
            conan_ref,
            (project_conan_path / "conanfile.py").resolve(),
            list(),
            list(),
            repo,
            github_client.get_repo(f"{org}/{gh_repo}") if github_client else None,
        )
        editables.append(editable)

    for ed in editables:
        create_editable_dependency(ed, editables)

    loading_editables_spinner.succeed()

    return editables

def get_editable_status(editable, dependency_graph):
    pass
