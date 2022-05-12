from colorama import Fore, Back, Style
from dataclasses import dataclass
from git import Repo
from github import Github, enable_console_debug_logging, GithubException, BadCredentialsException, TwoFactorException
from halo import Halo
from pathlib import Path
from xdg import xdg_config_home

import click
import yaml

import ast
from configparser import ConfigParser
import os
import re

#Will work when we use conan 2
#import sys
#import importlib.util
#import inspect

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
    repo: Repo
    gh_org_or_user: str
    updated: bool = False

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

def create_editable_dependency(editable, editables):
    #Avoid polluting conan directory with pycache
    #sys.dont_write_bytecode = True

    #conanfile_path = str(editable.conan_path)
    #conanfile_spec = importlib.util.spec_from_file_location('*', conanfile_path)
    #conanfile_module = importlib.util.module_from_spec(conanfile_spec)
    #conanfile_spec.loader.exec_module(conanfile_module)
    #members = inspect.getmembers(conanfile_module, inspect.isclass)
    all_required_lib = []
    with open(editable.conan_path, 'r') as conanfile:
        conanfile_ast = ast.parse(conanfile.read())
        for node in ast.iter_child_nodes(conanfile_ast):
            if isinstance(node, ast.ClassDef):
                for class_node in ast.iter_child_nodes(node):
                    if isinstance(class_node, ast.Assign):
                        for target in class_node.targets:
                            if target.id == 'requires':
                                all_required_lib.append([elt.value for elt in class_node.value.elts])

    #for name, member in members:
    #    if conanfile_module.ConanFile in member.mro()[1:]:
    #        for k, v in inspect.getmembers(member):
    #            if k == 'requires':
    #                all_required_lib = v

    #for other_editable in [x for x in editables if x is not editable]:
    #    for dep in all_required_lib:
    #        if dep.split('/')[0] == other_editable.name:
    #            dependency = get_dependency_from_name(dep)
    #            dependency.editable = other_editable
    #            editable.required_lib.append(dependency)

    #Restore pycache creation
    #sys.dont_write_bytecode = False

def print_index(repo):
    for diff in repo.index.diff(repo.head.commit):
        click.echo(f'{Fore.GREEN}{change_type_to_str[diff.change_type]}: {diff.a_path}', color=True)
    for diff in repo.index.diff(None):
        click.echo(f'{Fore.RED}{change_type_to_str[diff.change_type]}: {diff.a_path}', color=True)
    for path in repo.untracked_files:
        click.echo(f'{Fore.RED}Untracked files: {path}', color=True)

    click.echo(Fore.RESET, nl=False)

def create_editable_from_workspace(workspace_path: Path, workspace_data):
    editables = list()

    workspace_base_path = workspace_path.parents[0]

    for name, path in workspace_data['editables'].items():
        project_conan_path = (workspace_base_path / path['path'])
        short_name = name.split('/')[0]
        repo = Repo(project_conan_path.parents[0].resolve())
        remote_url = list(repo.remote('origin').urls)[0]
        match = re.search(rf'github.com:(.*)/(.*)', remote_url)
        if match:
            org = match.group(1)
            editable = Editable(
                name,
                short_name,
                (project_conan_path / 'conanfile.py').resolve(),
                list(),
                repo,
                org
            )
            editables.append(editable)
        else:
            raise Exception

    for ed in editables:
        create_editable_dependency(ed, editables)

    return editables


def update_push_and_commit(editable):
    repo = editable.repo
    add_and_commit = False

    number_changed_files = len(repo.index.diff(None)) + len(repo.index.diff('HEAD')) + len(repo.untracked_files)
    if number_changed_files > 0:
        click.echo('You have some file in your index')
        print_index(repo)
        add_and_commit = click.confirm('Do you want to add and commit those changes ?')
    else:
        click.echo(f'- {Fore.GREEN}Git repository is clean{Fore.RESET}')

    if add_and_commit:
        commit_msg = click.prompt(f'Select your commit message', default=f'Publishing {repo_basename} new version')
        repo.git.add('.')
        repo.git.commit(f'-m {commit_msg}')
    elif number_changed_files > 0:
        click.get_text_stream('stdout').write('\033[A\r\033[K')
        click.get_text_stream('stdout').write('\033[A\r\033[K')
        click.get_text_stream('stdout').write('\033[A\r\033[K')
        click.echo(click.style(f'{Fore.YELLOW}ℹ {Fore.RESET}', bold=True),nl=False)
        click.echo(f'Skipping commit and push')

def find_updatable_editable(editables):
    updatables = list()
    for ed in [ed for ed in editables if not ed.updated]:
        updatable = True
        for lib in ed.required_lib:
            if not lib.editable.updated:
                updatable = False

        if updatable:
            updatables.append(ed)

    return updatables

def update_conan_file(updatable, updated_editables):
    file_lines = list()
    with open(updatable.conan_path, 'r') as conanfile:
        file_lines = conanfile.readlines()

    for updated_editable in updated_editables:
        for i, line in enumerate(file_lines):
            name_regex = re.compile(rf'(.*)(({updated_editable.name})/(\w+)\@(.*))"\)(,?)')
            match = name_regex.search(line)
            if match:
                lib_version = match.group(4)

                if lib_version != updated_editable.repo.head.commit.hexsha[0:10]:
                    replacement = f'{match.group(1)}{match.group(3)}/{updated_editable.repo.head.commit.hexsha[0:10]}@{match.group(5)}"){match.group(6)}\n'
                    file_lines[i] = replacement
                    click.echo(f'{Fore.YELLOW}{match.group(3)}/{match.group(4)}@{match.group(5)} {Fore.RESET}-> {Fore.CYAN}{match.group(3)}/{updated_editable.repo.head.commit.hexsha[0:10]}@{match.group(5)}{Fore.RESET}')

    click.echo()

    with open(updatable.conan_path, 'w') as conanfile:
        conanfile.writelines(file_lines)

def update_workspace(editables: [Editable], workspace_path: Path, workspace_data):
    for name, path in workspace_data['editables'].items():
        for editable in editables:
            match = re.search(rf'(.*)(({editable.name})/(\w+)\@(.*))', name)
            if match:
                lib_version = match.group(4)
                if lib_version != editable.repo.head.commit.hexsha[0:10]:
                    click.echo(f'{Style.DIM}Switching {Fore.LIGHTCYAN_EX}{editable.name}{Fore.RESET} version in workspace.yml:{Style.RESET_ALL} {Fore.YELLOW}{match.group(3)}/{match.group(4)}@{match.group(5)} {Fore.RESET}-> {Fore.CYAN}{match.group(3)}/{editable.repo.head.commit.hexsha[0:10]}@{match.group(5)}{Fore.RESET}')


def update_editable(updatable: Editable, updated_editables: [Editable], workspace_path: Path):
    update_conan_file(updatable, updated_editables)
    update_push_and_commit(updatable)
    updatable.updated = True
    return updatable

@click.group()
def be_helpful():
    pass

@click.command()
@click.option("--repo", "-r", default=".", show_default=True)
@click.option("--github-token", "-gt")
@click.argument("workspace")
@click.pass_context
def publish(ctx, repo, github_token, workspace):
    #Setting up github
    config_path = xdg_config_home() / 'shred-project-helper/sph.ini'
    github = None
    config = ConfigParser()

    if not os.path.exists(config_path):
        click.echo('⚙ Creating config')
        click.echo()
        config['github'] = {'access_token': None}
        os.mkdir(xdg_config_home() / 'shred-project-helper')
        with open(config_path, 'w+') as config_file:
            config.write(config_file)
    else:
        config.read(config_path)

        if not github_token:
            github_token = config['github']['access_token']

    if github_token and 'access_token' in config['github']:
        save_token = click.prompt('Save access token to config?')
        if save_token:
            config['github']['access_token'] = github_token


    click.echo(f'Publishing library at {repo}')
    click.echo()

    try:
        if not github_token:
            github_username = click.prompt('Github username')
            github_password = click.prompt('Github password')
            github = Github(github_username, github_password)
        else:
            github = Github(github_token)

        user = github.get_user()
        click.echo(f'Logged in github as {user.login}')

    except BadCredentialsException as e:
        click.echo('Wrong github credentials')
        ctx.abort()
    except TwoFactorException as e:
        click.echo('Can\'t use credentials for account with 2FA. Please use an access token.')
        ctx.abort()
    except GithubException as e:
        click.echo('Github issue')
        click.echo(e)
        ctx.abort()

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

    loading_editables_spinner = Halo(text='Retrieving editables', spinner='dots')
    loading_editables_spinner.start()
    editables = create_editable_from_workspace(workspace_path, workspace_data)
    updated_editables = list()
    loading_editables_spinner.succeed()
    click.echo()

    updating_editables_spinner = Halo(text='Updating editables', spinner='dots')
    updating_editables_spinner.stop_and_persist('⟳')
    click.echo()

    while not all([e.updated for e in editables]):
        updatables = find_updatable_editable(editables)

        for updatable in updatables:
            click.echo(f'{Style.DIM}Updating editable: {updatable.name}{Style.RESET_ALL}')
            updated_editables.append(update_editable(updatable, updated_editables, workspace_path))
            click.echo()

    updating_workspace_spinner = Halo(text='Updating workspace', spinner='dots')
    updating_workspace_spinner.stop_and_persist('⟳')
    click.echo()

    update_workspace(editables, Path(workspace_path), workspace_data)


    #create_editable_dependency([updated_editable] + editables)
    #create_dependency_tree(editables, updated_editable)

be_helpful.add_command(publish)
