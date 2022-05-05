from dataclasses import dataclass
import click
import importlib.util
import inspect
import os
import yaml
from git import Repo
from pathlib import Path
from colorama import Fore, Back, Style

change_type_to_str={
    "D": "New file",
    "A": "Deleted file",
    "R": "Renamed file",
    "M": "Modified file",
    "T": "Type of file changed (e.g. symbolic link became a file)"
}

@dataclass
class Dependency:
    full_name: str
    name: str
    editable = None

@dataclass
class Editable:
    full_name: str
    name: str
    conan_path: Path
    required_lib: [Dependency]

dependency_list = dict()

@dataclass
class EditableTree:
    node: Editable
    children: [Editable]

def get_dependency_from_name(name: str):
    if name not in dependency_list:
        dependency_list[name] = Dependency(name, name.split('/')[0])

    return dependency_list[name]

def get_editable_from_dependency(dep: Dependency, editables: [Editable] = []):
    if not dep.editable:
        for ed in editables:
            if dep.name == ed.name:
                dep.editable = ed

    return dep.editable

def create_editable_dependency(editables):
    sort_editables = []

    for editable in editables:
        conanfile_path = str((editable.conan_path / 'conanfile.py').resolve())
        conanfile_spec = importlib.util.spec_from_file_location('*', conanfile_path)
        conanfile_module = importlib.util.module_from_spec(conanfile_spec)
        conanfile_spec.loader.exec_module(conanfile_module)
        members = inspect.getmembers(conanfile_module, inspect.isclass)
        all_required_lib = []

        for name, member in members:
            if conanfile_module.ConanFile in member.mro()[1:]:
                for k, v in inspect.getmembers(member):
                    if k == 'requires':
                        all_required_lib = v

        for other_editable in [x for x in editables if x is not editable]:
            for dep in all_required_lib:
                if dep.split('/')[0] == other_editable.name:
                    dependency = get_dependency_from_name(dep)
                    dependency.editable = other_editable
                    editable.required_lib.append(dependency)

def print_index(repo):
    for diff in repo.index.diff(repo.head.commit):
        click.echo(f'{Fore.GREEN} {change_type_to_str[diff.change_type]}: {diff.a_path}', color=True)
    for diff in repo.index.diff(None):
        click.echo(f'{Fore.RED} {change_type_to_str[diff.change_type]}: {diff.a_path}', color=True)

    click.echo(Fore.RESET)

@click.group()
def be_helpful():
    pass

@click.command()
@click.option("--repo", "-r", default=".", show_default=True)
@click.argument("workspace")
@click.pass_context
def publish(ctx, repo, workspace):
    repo_path = Path(repo)
    repo_basename = os.path.basename(repo_path.absolute())
    repo = Repo(repo_path)
    add_and_commit = False

    if len(list(repo.index.iter_blobs())) > 0:
        click.echo('You have some file in your index')
        print_index(repo)
        add_and_commit = click.confirm('Do you want to add and commit those changes ?')

    if add_and_commit:
        commit_msg = click.prompt(f'Select your commit message', default=f'Publishing {repo_basename} new version')
        repo.git.add('.')
        repo.git.commit(f'-m {commit_msg}')

    conan_version_tag = repo.head.commit.hexsha[0:10]

    click.echo('Updating workspace')

    workspace_path = Path(workspace)
    if not workspace_path.is_file():
        workspace_path = workspace_path / 'workspace.yml'

    workspace_data = None
    try:
        with open(workspace_path.resolve(), 'r') as workspace_file:
            try:
                workspace_data = yaml.full_load(workspace_file)
            except yaml.YAMLError as exc:
                click.echo(f'Can\'t parse file {workspace_path}')
                click.echo(exc)
                ctx.abort()
    except OSError as exc:
        click.echo(f'Can\'t open file {workspace_path}')
        click.echo(exc)
        ctx.abort()

    root_name = workspace_data['root']

    updated_editables = [Editable(k, k.split('/')[0], (workspace_path.parents[0] / v['path']).resolve(), list()) for k, v in workspace_data['editables'].items() if (workspace_path.parents[0] / v['path']).resolve() == (repo_path / 'conan').resolve()]
    editables = [Editable(k, k.split('/')[0], (workspace_path.parents[0] / v['path']).resolve(), list()) for k, v in workspace_data['editables'].items() if (workspace_path.parents[0] / v['path']).resolve() != (repo_path / 'conan').resolve()]

    create_editable_dependency(updated_editables + editables)
    for editable in editables:
        click.echo(f'Updating editable: {editable.name}')
        click.echo(editable.required_lib)

be_helpful.add_command(publish)
