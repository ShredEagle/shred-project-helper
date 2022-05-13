import ast
import os
import re
import time
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path

import click
import yaml
from colorama import Fore, Style
from git import Repo
from github import (BadCredentialsException,  # enable_console_debug_logging,
                    Github, GithubException, TwoFactorException)
from halo import Halo
from xdg import xdg_config_home

# Will work when we use conan 2
# import sys
# import importlib.util
# import inspect

change_type_to_str = {
    "D": "New file",
    "A": "Deleted file",
    "R": "Renamed file",
    "M": "Modified file",
    "T": "Type of file changed (e.g. symbolic link became a file)"
}

github_client = None


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
    gh_repo: str
    updated: bool = False


dependency_list = dict()


def delete_term_n_previous_line(n):
    for i in range(n):
        click.get_text_stream('stdout').write('\033[A\r\033[K')


def get_dependency_from_name(name: str):
    global dependency_list
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
    all_required_lib = []
    with open(editable.conan_path, 'r') as conanfile:
        conanfile_ast = ast.parse(conanfile.read())
        for node in ast.iter_child_nodes(conanfile_ast):
            if isinstance(node, ast.ClassDef):
                for class_node in ast.iter_child_nodes(node):
                    if isinstance(class_node, ast.Assign):
                        for target in class_node.targets:
                            if target.id == 'requires':
                                all_required_lib += [elt.value
                                                         for elt in
                                                         class_node.value.elts
                                                         ]
    for other_editable in [x for x in editables if x is not editable]:
        for dep in all_required_lib:
            if dep.split('/')[0] == other_editable.name:
                dependency = get_dependency_from_name(dep)
                dependency.editable = other_editable
                editable.required_lib.append(dependency)


def print_index(repo):
    for diff in repo.index.diff(repo.head.commit):
        click.echo(f'{Fore.GREEN}{change_type_to_str[diff.change_type]}:' +
                   f' {diff.a_path}', color=True)
    for diff in repo.index.diff(None):
        click.echo(f'{Fore.RED}{change_type_to_str[diff.change_type]}:' +
                   f' {diff.a_path}', color=True)
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
        match = re.search(r'github.com:(.*)/(.*).git', remote_url)
        if match:
            org = match.group(1)
            gh_repo = match.group(2)
            editable = Editable(
                name,
                short_name,
                (project_conan_path / 'conanfile.py').resolve(),
                list(),
                repo,
                org,
                gh_repo
            )
            editables.append(editable)
        else:
            raise click.Abort()

    for ed in editables:
        create_editable_dependency(ed, editables)

    return editables


def wait_for_run_to_complete(gh_repo_client, repo):
    waiting_for_run = Halo('Waiting for workflow to start', spinner='dots')
    waiting_for_run.start()
    current_run = None
    for i in range(10):
        runs_queued = gh_repo_client.get_workflow_runs(
            branch='develop', status='queued'
        )
        runs_in_progress = gh_repo_client.get_workflow_runs(
            branch='develop', status='in_progress'
        )
        if runs_queued.totalCount > 0 or runs_in_progress.totalCount > 0:
            for run in runs_queued:
                if run.head_sha == repo.head.commit.hexsha:
                    current_run = run
            if current_run:
                break
        time.sleep(2)

    waiting_for_run.stop()

    run_progress = Halo(f'Workflow {current_run.status}. Waiting for the end')
    run_progress.start()
    status = current_run.status
    if current_run:
        while current_run.status != 'completed':
            if current_run.status != status:
                run_progress.stop()
                run_progress = Halo(f'Workflow {current_run.status}. Waiting for the end')
                run_progress.start()

            status = current_run.status
            current_run = gh_repo_client.get_workflow_run(current_run.id)
            time.sleep(2)

        if current_run.conclusion == 'success':
            run_progress.succeed('Workflow completed with success')
            click.echo()
        else:
            run_progress.fail('Workflow failed')
            raise click.Abort()
    else:
        Halo('Can\'t find a workflow run associated with this commit').fail()
        raise click.Abort()


def is_there_a_completed_run(gh_repo_client, repo):
    # We did not push look for a completed run
    runs_completed = gh_repo_client.get_workflow_runs(
        branch='develop', status='completed'
    )

    run_is_completed = False
    if runs_completed.totalCount > 0:
        for run in runs_completed:
            if run.head_sha == repo.head.commit.hexsha:
                run_is_completed = True

    return run_is_completed


def check_state_of_repo_and_commit(editable):
    repo = editable.repo
    add_and_commit = False

    if repo.active_branch.name != 'develop':
        click.echo('You need to be on the develop branch to update dependency')
        switch_branch = click.prompt('Switch branch to develop')

        if switch_branch:
            repo.heads.develop.checkout()
            delete_term_n_previous_line(2)
            Halo(text="Switched repo to develop").succeed()
            click.echo()
        else:
            Halo(text='Could not switch to the develop branch').fail()
            raise click.Abort()

    number_changed_files = len(repo.index.diff(None))
    + len(repo.index.diff('HEAD'))
    + len(repo.untracked_files)

    if number_changed_files > 0:
        click.echo('You have some file in your index')
        print_index(repo)
        add_and_commit = click.confirm(
            'Do you want to add and commit those changes ?'
        )
    else:
        Halo('Git repository is clean').succeed()
        click.echo()

    if add_and_commit:
        commit_msg = click.prompt(
            'Select your commit message',
            default=f'Publishing {editable.name} new version'
        )
        repo.git.add('.')
        repo.git.commit(f'-m {commit_msg}')
        delete_term_n_previous_line(4 + number_changed_files)
        Halo(f'Change commited with message {commit_msg}').succeed()
        click.echo()
    elif number_changed_files > 0:
        delete_term_n_previous_line(3 + number_changed_files)
        click.echo(click.style(f'{Fore.YELLOW}ℹ {Fore.RESET}',
                               bold=True), nl=False)
        click.echo('Skipping commit and push')
        return False

    return True


def commit_conanfile_changes(editable, conanfile_update_names):
    number_changed_files = len(editable.repo.index.diff(None))
    + len(editable.repo.index.diff('HEAD'))
    + len(editable.repo.untracked_files)

    if number_changed_files > 0:
        try:
            version_update_str = [
                f'{name} to {version}' for name, version in conanfile_update_names
            ]
            commit_msg = f'Updating {"".join(version_update_str)}'
            editable.repo.git.add('.')
            editable.repo.git.commit(f'-m {commit_msg}')
            Halo('Conanfile version update commited automatically').succeed()
            click.echo()
        except Exception:
            Halo('Could not auto commit version update in conanfile').fail()
            raise click.Abort()


def push_to_github(editable):
    gh_repo_client = github_client.get_repo(
        f'{editable.gh_org_or_user}/{editable.gh_repo}'
    )

    commit = gh_repo_client.get_commit('develop')

    need_to_push = commit.sha != editable.repo.head.commit.hexsha
    if need_to_push:
        we_need_to_push = Halo('Pushing to github', spinner='dots')
        we_need_to_push.start()
        res = editable.repo.remote('origin').push()
        if len(res) == 0:
            we_need_to_push.fail('Cannot push to github. Aborting')
            raise click.Abort()
        else:
            we_need_to_push.succeed('Pushed to github')
            click.echo()


def wait_for_workflow(editable):
    gh_repo_client = github_client.get_repo(
        f'{editable.gh_org_or_user}/{editable.gh_repo}'
    )
    completed_run = Halo('Looking for a completed run')
    completed_run.start()
    if is_there_a_completed_run(gh_repo_client, editable.repo):
        completed_run.succeed('There is a completed run for this commit. ' +
                              'Skipping workflow run')
        click.echo()
        return
    else:
        completed_run.stop()

    wait_for_run_to_complete(gh_repo_client, editable.repo)


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
    conanfile_update_names = list()
    file_lines = list()
    file_lines_update = False
    with open(updatable.conan_path, 'r') as conanfile:
        file_lines = conanfile.readlines()

    for updated_editable in updated_editables:
        for i, line in enumerate(file_lines):
            name_regex = re.compile(
                rf'(.*)(({updated_editable.name})/(\w+)\@(.*))"\)(,?)'
            )
            match = name_regex.search(line)
            if match:
                lib_version = match.group(4)

                if (
                    lib_version !=
                    updated_editable.repo.head.commit.hexsha[0:10]
                ):
                    file_lines_update = True
                    replacement = (
                        f'{match.group(1)}{match.group(3)}/' +
                        f'{updated_editable.repo.head.commit.hexsha[0:10]}' +
                        f'@{match.group(5)}"){match.group(6)}\n'
                    )
                    conanfile_update_names.append(
                        (
                            updated_editable.name,
                            updated_editable.repo.head.commit.hexsha[0:10]
                        )
                    )
                    file_lines[i] = replacement
                    click.echo(
                        f'{Fore.YELLOW}{match.group(3)}/{match.group(4)}@' +
                        f'{match.group(5)} {Fore.RESET}-> ' +
                        f'{Fore.CYAN}{match.group(3)}/' +
                        f'{updated_editable.repo.head.commit.hexsha[0:10]}@' +
                        f'{match.group(5)}{Fore.RESET}'
                    )

    if file_lines_update:
        click.echo()

    with open(updatable.conan_path, 'w') as conanfile:
        conanfile.writelines(file_lines)

    return conanfile_update_names


def update_workspace(
        editables: [Editable], workspace_path: Path, workspace_data
):
    updated_workspace = False
    for name, path in workspace_data['editables'].copy().items():
        for editable in editables:
            match = re.search(rf'(.*)(({editable.name})/(\w+)\@(.*))', name)
            if match:
                lib_version = match.group(4)
                if lib_version != editable.repo.head.commit.hexsha[0:10]:
                    updated_workspace = True
                    new_version = (
                        f'{match.group(3)}/' +
                        f'{editable.repo.head.commit.hexsha[0:10]}' +
                        f'@{match.group(5)}'
                    )
                    old_version = (
                        f'{match.group(3)}/' +
                        f'{match.group(4)}@{match.group(5)}'
                    )

                    click.echo(
                        f'{Style.DIM}' +
                        f'Switching {Fore.LIGHTCYAN_EX}{editable.name}' +
                        f'{Fore.RESET} version in workspace.yml:' +
                        f'{Style.RESET_ALL} {Fore.YELLOW}{match.group(3)}/' +
                        f'{match.group(4)}@{match.group(5)} {Fore.RESET}->' +
                        f' {Fore.CYAN}{match.group(3)}/' +
                        f'{editable.repo.head.commit.hexsha[0:10]}' +
                        f'@{match.group(5)}{Fore.RESET}'
                    )
                    workspace_data['editables'][new_version] = path
                    del workspace_data['editables'][old_version]

    if updated_workspace:
        click.echo()

    with open(workspace_path, 'w') as file:
        file.write(yaml.dump(workspace_data))

    repo = Repo(workspace_path.parents[0])
    number_changed_files = len(repo.index.diff(None))
    + len(repo.index.diff('HEAD'))
    + len(repo.untracked_files)

    if number_changed_files > 0:
        repo.git.add('.')
        repo.git.commit('-m updating workspace')

    we_need_to_push = Halo('Pushing workspace to github', spinner='dots')
    we_need_to_push.start()
    res = repo.remote('origin').push()
    we_need_to_push.stop()
    if len(res) == 0:
        we_need_to_push.fail('Cannot push to github. Aborting')
        raise click.Abort()
    else:
        we_need_to_push.succeed('Pushed workspace to github')

def update_editable(
        updatable: Editable,
        updated_editables: [Editable],
        workspace_path: Path):
    clean = check_state_of_repo_and_commit(updatable)
    conanfile_update_names = update_conan_file(updatable, updated_editables)
    if clean:
        commit_conanfile_changes(updatable, conanfile_update_names)
    else:
        Halo('Can\'t auto update conan file without a clean repo').warn()
    push_to_github(updatable)
    wait_for_workflow(updatable)
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
    global github_client
    # Setting up github
    config_path = xdg_config_home() / 'shred-project-helper/sph.ini'
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
            github_client = Github(github_username, github_password)
        else:
            github_client = Github(github_token)

        user = github_client.get_user()
        Halo(f'Logged in github as {user.login}').succeed()
        click.echo()

    except BadCredentialsException as e:
        click.echo('Wrong github credentials')
        click.echo(e)
        ctx.abort()
    except TwoFactorException as e:
        click.echo(
            'Can\'t use credentials for account with 2FA. Please use an' +
            ' access token.'
        )
        click.echo(e)
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

    loading_editables_spinner = Halo(
        text='Retrieving editables', spinner='dots'
    )
    loading_editables_spinner.start()

    editables = create_editable_from_workspace(workspace_path, workspace_data)

    loading_editables_spinner.succeed()
    click.echo()

    Halo(
        text='Updating editables'
    ).stop_and_persist('⟳')
    click.echo()

    updated_editables = list()

    while not all([e.updated for e in editables]):
        updatables = find_updatable_editable(editables)

        for updatable in updatables:
            click.echo(
                f'{Style.DIM}Updating editable: ' +
                f'{updatable.name}{Style.RESET_ALL}'
            )
            click.echo()
            updated_editables.append(
                update_editable(updatable, updated_editables, workspace_path))

    updating_workspace_spinner = Halo(
        text='Updating workspace',
        spinner='dots'
    )
    updating_workspace_spinner.stop_and_persist('⟳')
    click.echo()

    update_workspace(editables, Path(workspace_path), workspace_data)


be_helpful.add_command(publish)
