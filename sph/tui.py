import asyncio
import curses
import functools
import os

import click
from sph.conan_context import ConanContext
from sph.ui import SphUi

from sph.config import configCreate, configSaveToken


def main_tui(github_token, workspace_dir, stdscr):
    context = ConanContext(workspace_dir, github_token)
    ui = SphUi(stdscr, context)
    running = True

    while running: 
        try:
            asyncio.run(ui.draw())
        except (KeyboardInterrupt, SystemExit):
            running = False
            context.stop_context()


@click.command()
@click.option("--github-token", "-gt")
@click.argument("workspace_dir")
def tui(github_token, workspace_dir):
    github_client = None

    config, config_path = configCreate()

    if github_token:
        configSaveToken(config, config_path, github_token)

    github_token = config["github"]["access_token"]

    if not github_token:
        click.echo("Needs a github token")
        raise click.Abort()

    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(functools.partial(main_tui, github_token, workspace_dir))
