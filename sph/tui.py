import os
from pathlib import Path

import py_cui
import click

from github import (BadCredentialsException, Github, GithubException,
                    TwoFactorException)

from sph.config import configCreate, configSaveToken
from sph.workspace import Workspace


@click.command()
@click.option("--github-token", "-gt")
@click.argument("workspace_dir")
def tui(github_token, workspace_dir):
    github_client = None;

    config, config_path = configCreate()

    if github_token:
        configSaveToken(config, config_path, github_token)

    github_token = config['github']['access_token']

    try:
        if not github_token:
            github_username = click.prompt('Github username')
            github_password = click.prompt('Github password')
            github_client = Github(github_username, github_password)
        else:
            github_client = Github(github_token)

        user = github_client.get_user()
    except BadCredentialsException as e:
        click.echo('Wrong github credentials')
        click.echo(e)
        raise click.Abort()
    except TwoFactorException as e:
        click.echo(
            'Can\'t use credentials for account with 2FA. Please use an' +
            ' access token.'
        )
        click.echo(e)
        raise click.Abort()
    except GithubException as e:
        click.echo('Github issue')
        click.echo(e)
        raise click.Abort()

    files = [Workspace(Path(workspace_dir) / Path(x)) for x in os.listdir(workspace_dir) if "yml" in x]

    root = py_cui.PyCUI(8, 8)
    root.set_title('Hello')
    root.toggle_unicode_borders()
    ws_list = root.add_scroll_menu('Workspaces', 0, 0, row_span=8, column_span=2)
    ws_list.add_item_list(files)

    root_block = root.add_scroll_menu('Roots', 0, 2, row_span=1, column_span=6)

    selected_root = None

    def select_ws():
        root_block.clear()
        workspace: Workspace = ws_list.get()
        root_block.add_item_list([f"{ref.conan_ref} ({path.resolve().parents[0]})" for (ref, path) in workspace.editables])
        root.move_focus(root_block)

    ws_list.add_key_command(py_cui.keys.KEY_ENTER, select_ws)
    root.move_focus(ws_list)
    root.add_scroll_menu('Menu 3', 1, 2, row_span=7, column_span=6)
    root.start()
