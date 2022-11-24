import os
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor
import click
import curses
from github import BadCredentialsException, Github, GithubException, TwoFactorException

from sph.config import configCreate, configSaveToken
from sph.conflict import compute_conflicts
from sph.editable import create_editable_from_workspace_list
from witch import witch_init, start_frame, end_frame, start_layout, end_layout
from witch.layout import HORIZONTAL, VERTICAL
from witch.utils import Percentage
from witch.widgets import start_panel, end_panel, text_item, start_same_line, text_buffer, end_same_line
from witch.state import add_text_color, set_cursor

from sph.workspace import Workspace

class Runner:

    def __init__(self, workspace_dir, gh_client, thread_pool):
        self.thread_pool = thread_pool
        self.workspaces = []
        self.editable_list = []
        self.workspace_dir = workspace_dir
        self.gh_client = gh_client
        self.running = True
        self.workspace_opened = set()
        self.hovered_root = None

    def main_loop(self, astdscr):
        witch_init(astdscr)
        add_text_color("refname", curses.COLOR_YELLOW)
        add_text_color("path", curses.COLOR_CYAN)
        add_text_color("success", curses.COLOR_GREEN)
        add_text_color("fail", curses.COLOR_RED)

        while True:
            self.hovered_root = None

            start_frame()

            start_layout("base", HORIZONTAL, Percentage(100))

            start_panel("Workspaces", Percentage(20), Percentage(100))
            for ws in self.workspaces:
                _, pressed = text_item(ws.path.name)
                if pressed:
                    if ws in self.workspace_opened:
                        self.workspace_opened.remove(ws)
                    else:
                        self.workspace_opened.add(ws)


                if ws in self.workspace_opened:
                    for ref, path in [(ref, path) for ref, path in ws.local_refs if ref.ref in [x.ref for x in ws.root]]:
                        hovered_root, _ = text_item([(f"  {ref.ref}", "refname")])
                        if hovered_root:
                            self.hovered_root = ref
            end_panel()

            if self.hovered_root:
                root_editable = self.get_editable_from_ref(self.hovered_root)

                editables = [root_editable]
                for ref in root_editable.required_local_lib:
                    editables.append(self.get_editable_from_ref(ref))

                start_panel("Root check", Percentage(80), Percentage(100))
                for ed in editables:
                    if ed and ed.is_local:
                        text_item([(f"{ed.package.name}", "refname"), " at ", (f"{ed.conan_path.parents[1]}", "path")])
                        if ed.repo.is_dirty():
                            text_item([(" ", "fail"), ("Repo is dirty")])
                        else:
                            text_item([(" ", "success"), ("Repo is clean")])
                            if ed.current_run and ed.current_run.status == "completed":
                                if ed.current_run.conclusion == "success":
                                    text_item([(" ", "success"), ("CI success")])
                                else:
                                    text_item([(" ", "fail"), ("CI failure")])
                            if ed.current_run and ed.current_run.status == "in_progress":
                                pass
                        for req in ed.required_local_lib:
                            req.print_check_tui(1)
                        for req in ed.required_external_lib:
                            req.print_check_tui(1)

                        text_item("")
                end_panel()

            end_layout()

            end_frame()

    def run_ui(self):
        curses.wrapper(self.main_loop)

    def load_stuff_and_shit(self):
        self.workspaces = [Workspace(Path(self.workspace_dir) / Path(x)) for x in os.listdir(self.workspace_dir) if "yml" in x]
        self.editable_list = create_editable_from_workspace_list(self.workspaces, self.gh_client, self.thread_pool)
        compute_conflicts(self.workspaces, self.editable_list)

    def get_editable_from_ref(self, conan_ref):
        try:
            return next(e for e in self.editable_list if e.package == conan_ref.package)
        except StopIteration:
            return None

@click.command()
@click.option("--github-token", "-gt")
@click.argument("workspace_dir")
def new_tui(github_token, workspace_dir):
    thread_pool = ThreadPoolExecutor(max_workers=20)
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

    runner = Runner(workspace_dir, github_client, thread_pool)

    try:
        work = thread_pool.submit(runner.load_stuff_and_shit)
        runner.run_ui()
    except (KeyboardInterrupt, SystemExit) as e:
        print(e)
        work.cancel()
        while not work.done():
            pass
        global running
        running = False
