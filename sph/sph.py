import re
from pathlib import Path

import click
from colorama import Fore
import yaml
from halo import Halo

from sph.publish import publish
from sph.editable import create_editable_from_workspace


@click.command()
@click.argument("workspace")
def setup(workspace):
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
                raise click.Abort()

    except OSError as exc:
        click.echo(f'Can\'t open file {workspace_path}')
        click.echo(exc)
        raise click.Abort()

    loading_editables_spinner = Halo(
        text='Retrieving editables', spinner='dots'
    )
    loading_editables_spinner.start()

    editables = create_editable_from_workspace(
        workspace_path, workspace_data
    )

    loading_editables_spinner.succeed()
    click.echo()

    for ed in editables:
        match = re.search(rf'(.*)(({ed.name})/(\w+)\@(.*))', ed.full_name)
        if match:
            sha = match.group(4)
            if not ed.repo.is_dirty():
                click.echo()
                click.echo(click.style(f'{Fore.YELLOW}ℹ {Fore.RESET}',
                                       bold=True), nl=False)
                click.echo(f'Checking out {ed.name} at {sha}')
                try:
                    ed.repo.git.checkout(sha)
                    Halo(
                        f'Successfuly checked out {ed.name} at {sha}'
                    ).succeed()
                except Exception:
                    Halo(f'Couldn\'t checkout {ed.name} at {sha}').fail()
            else:
                Halo(f'Can\'t checkout {ed.name} at {sha}. It is dirty.').fail()


@click.group()
def be_helpful():
    pass


be_helpful.add_command(publish)
be_helpful.add_command(setup)
