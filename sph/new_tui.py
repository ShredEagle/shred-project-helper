import os
from time import perf_counter
from itertools import accumulate

from typing import Optional
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor
import click
import curses
from github import BadCredentialsException, Github, GithubException, TwoFactorException

from sph.config import configCreate, configSaveToken
from sph.conflict import compute_conflicts
from sph.editable import Editable, create_editable_from_workspace_list
from witch import witch_init, start_frame, end_frame, start_layout, end_layout
from witch.layout import HORIZONTAL, VERTICAL
from witch.utils import Percentage
from witch.widgets import start_panel, end_panel, text_item, start_same_line, end_same_line, start_floating_panel, end_floating_panel, POSITION_CENTER
from witch.state import add_text_color, selected_id, input_buffer, is_key_pressed, set_selected_id

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
        self.root_opened = set()
        self.hovered_root = None
        self.selected_ref_with_editable = None

    def main_loop(self, astdscr):
        witch_init(astdscr)
        add_text_color("refname", curses.COLOR_YELLOW)
        add_text_color("path", curses.COLOR_CYAN)
        add_text_color("success", curses.COLOR_GREEN)
        add_text_color("fail", curses.COLOR_RED)
        input_buffer_save = 0
        show_help = False
        old_id = ""

        frame_count = 0
        fps = [0] * 100
        start = 0
        end = 1

        while True:
            fps[frame_count % 100] = 1.0 / (end - start)
            real_fps = accumulate(fps)
            for i in real_fps:
                real_fps = i / 100
            start = perf_counter()
            frame_count += 1
            start_frame()

            if is_key_pressed('?'):
                old_id = selected_id()
                show_help = True

            start_layout("base", HORIZONTAL, Percentage(100) - 3)

            workspace_id = start_panel("Workspaces", Percentage(20), Percentage(100), start_selected=True)
            for ws in self.workspaces:
                _, pressed = text_item(ws.path.name)
                if pressed:
                    if ws in self.workspace_opened:
                        self.workspace_opened.remove(ws)
                    else:
                        self.workspace_opened.add(ws)


                if ws in self.workspace_opened:
                    for ref, _ in [(ref, path) for ref, path in ws.local_refs if ref.ref in [x.ref for x in ws.root]]:
                        root_editable = self.get_editable_from_ref(ref)
                        if not root_editable or not root_editable.is_local:
                            text_item([(f"  {ref.ref} not local", "refname")])
                            hovered_root = False
                            continue
                        else:
                            hovered_root, pressed = text_item([(f"  {ref.ref}", "refname")])
                        if hovered_root:
                            self.hovered_root = (ref, ws)
                            self.selected_ref_with_editable = None
                        if pressed:
                            if ref in self.root_opened:
                                self.root_opened.remove(ref)
                            else:
                                self.root_opened.add(ref)

                        if ref in self.root_opened:
                            root_editable = self.get_editable_from_ref(ref)
                            if root_editable:
                                for ref in root_editable.required_local_lib:
                                    conflict = ws.path in ref.conflicts and len(ref.conflicts[ws.path]) > 0
                                    symbol = " " if not conflict else ""
                                    _, pressed = text_item((f"  {symbol} {ref.ref}", "fail" if conflict else "path"))

                                    if pressed:
                                        self.selected_ref_with_editable = (ref, root_editable, ws)
                                        self.hovered_root = None
                                for ref in root_editable.required_external_lib:
                                    conflict = ws.path in ref.conflicts and len(ref.conflicts[ws.path]) > 0
                                    symbol = " " if not conflict else ""
                                    _, pressed = text_item((f"  {symbol} {ref.ref}", "fail" if conflict else "refname"))

                                    if pressed:
                                        self.selected_ref_with_editable = (ref, root_editable, ws)
                                        self.hovered_root = None
            end_panel()

            if self.hovered_root:
                ref, ws = self.hovered_root
                root_editable = self.get_editable_from_ref(ref)

                editables = [root_editable]
                for ref in root_editable.required_local_lib:
                    editables.append(self.get_editable_from_ref(ref))

                start_panel(f"{ref.package.name} check", Percentage(80), Percentage(100))
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
                            req.print_check_tui(ws.path)
                        for req in ed.required_external_lib:
                            req.print_check_tui(ws.path)

                        text_item("")
                end_panel()
            elif self.selected_ref_with_editable:
                selected_ref, selected_editable, ws = self.selected_ref_with_editable
                if selected_editable:
                    ref = selected_editable.get_dependency_from_package(selected_ref.package)
                    ref.fill_date_from_github(self.get_editable_from_ref(ref), self.thread_pool)

                    start_layout("ref_panel_and_log", VERTICAL, Percentage(80))
                    start_panel(f"{selected_ref.ref} conflict resolution", Percentage(100), Percentage(80), start_selected=True)
                    text_item("Choose a version to resolve the conflict (press enter to select)", selectable=False)
                    text_item(f"In {selected_editable.package} at {selected_editable.conan_path}", selectable=False)
                    text_item(f"  {ref} - {ref.date}")
                    for conflict in selected_ref.conflicts[ws.path]:
                        if isinstance(conflict, Workspace):
                            text_item(f"In {conflict.path.name}", selectable=False)
                            conflict_ref = conflict.get_dependency_from_package(selected_ref.package)
                            text_item(f"  {conflict_ref} - {conflict_ref.date}")
                            conflict_ref.fill_date_from_github(self.get_editable_from_ref(conflict_ref), self.thread_pool)
                        else:
                            conflict_editable = self.get_editable_from_ref(selected_editable.get_dependency_from_package(conflict))
                            if conflict_editable:
                                conflict_ref = conflict_editable.get_dependency_from_package(selected_ref.package)
                                text_item(f"In {conflict_editable.package} at {conflict_editable.conan_path.resolve()}", selectable=False)
                                text_item(f"  {conflict_ref} - {conflict_ref.date}")
                                conflict_ref.fill_date_from_github(self.get_editable_from_ref(conflict_ref), self.thread_pool)
                    end_panel()
                    if is_key_pressed(chr(27)):
                        self.selected_ref = None
                        set_selected_id(workspace_id)
                    start_panel("Workspace log", Percentage(100), Percentage(19))
                    end_panel()
                    end_layout()
            else:
                start_panel(f"Root check", Percentage(80), Percentage(100))
                end_panel()

            end_layout()

            if input_buffer() != -1:
                input_buffer_save = input_buffer()

            start_panel("hehe", Percentage(100), 3)
            text_item(real_fps)
            end_panel()

            if show_help:
                id = start_floating_panel("Help", POSITION_CENTER, Percentage(50), Percentage(80))
                start_same_line()
                text_item(("C", "path"), 10)
                text_item("Conan workspace install hovered workspace")
                end_same_line()
                end_floating_panel()
                set_selected_id(id)
                if is_key_pressed("q"):
                    set_selected_id(old_id)
                    show_help = False
            elif is_key_pressed("q"):
                raise SystemExit()


            end_frame()
            end = perf_counter()

    def run_ui(self):
        os.environ.setdefault('ESCDELAY', '25')
        curses.wrapper(self.main_loop)

    def load_stuff_and_shit(self):
        self.workspaces = [Workspace(Path(self.workspace_dir) / Path(x)) for x in os.listdir(self.workspace_dir) if "yml" in x]
        self.editable_list = create_editable_from_workspace_list(self.workspaces, self.gh_client, self.thread_pool)
        compute_conflicts(self.workspaces, self.editable_list)

    def get_editable_from_ref(self, conan_ref) -> Optional[Editable]:
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
    except (KeyboardInterrupt, SystemExit):
        work.cancel()
        while not work.done():
            pass
        global running
        running = False
