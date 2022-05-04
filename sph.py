import click
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
@click.option("--repo", "--r", default=".", show_default=True)
@click.argument("workspace")
def publish(repo, workspace):
    repo_path = Path(repo)
    repo_basename = os.path.basename(repo_path.absolute())
    repo = Repo(repo_path)

    if len(list(repo.index.iter_blobs())) > 0:
        click.echo('You have some file in your index')
        print_index(repo)
        add_and_commit = click.confirm('Do you want to add and commit those changes ?')

    if add_and_commit:
        commit_msg = click.prompt(f'Select your commit message', default=f'Publishing {repo_basename} new version')
        repo.git.add('.')
        repo.git.commit(f'-m {commit_msg}')


be_helpful.add_command(publish)
