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

def sort_editables(editables):
    return editables

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

    click.echo('Updating workspace')

    workspace_path = Path(workspace)
    if not workspace_path.is_file():
        workspace_path = workspace_path / 'workspace.yml'

    click.echo(workspace_path.resolve())

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
    conanfile_path = str((repo_path / 'conan/conanfile.py').resolve())
    click.echo(conanfile_path)
    conanfile_spec = importlib.util.spec_from_file_location('*', conanfile_path)
    conanfile_module = importlib.util.module_from_spec(conanfile_spec)
    conanfile_spec.loader.exec_module(conanfile_module)

    click.echo(inspect.getmembers(conanfile_module, inspect.isclass))
    non_root_editables = [(v['path'], k) for k, v in workspace_data['editables'].items() if k != root_name]
    root_editable = [(v['path'], k) for k, v in workspace_data['editables'].items() if k == root_name]

    sorted_to_update_editables, update_to_make = sort_editables(non_root_editables)
    for editable in sorted_non_root_editables:
        click.echo(f'Updating editables with path {editable}')

be_helpful.add_command(publish)
