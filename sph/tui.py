import os
import shutil
import re
import subprocess
from time import perf_counter
import threading
from itertools import accumulate

from typing import Optional
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor
import click
import curses
from github import BadCredentialsException, Github, GithubException, TwoFactorException
from sph.conan_ref import ConanRef

from sph.config import configCreate, configSaveToken
from sph.conflict import compute_conflicts
from sph.editable import Editable, create_editable_from_workspace_list
from sph.semver import Semver
from witchtui import witch_init, start_frame, end_frame, start_layout, end_layout
from witchtui.layout import HORIZONTAL, VERTICAL
from witchtui.utils import Percentage
from witchtui.widgets import end_status_bar, start_panel, end_panel, start_status_bar, text_buffer, text_item, start_same_line, end_same_line, start_floating_panel, end_floating_panel, POSITION_CENTER
from witchtui.state import add_text_color, selected_id, is_key_pressed, set_selected_id

from sph.workspace import Workspace

KEY_ESCAPE = chr(27)

class Runner:

    def __init__(self, workspace_dir, gh_client, thread_pool):
        self.thread_pool = thread_pool
        self.workspace_dir = workspace_dir
        self.gh_client = gh_client
        self.running = True

        # UI state
        self.workspace_opened = set()
        self.root_opened = set()
        self.hovered_root = None
        self.show_help = False

        # Workspace, ref and editable data
        self.selected_ref_with_editable = None
        self.workspaces = []
        self.editable_list = []
        self.github_rate = None
        self.conan_base_newest_version = None

        # Cached data
        self.conflict_log = []
        self.install_proc = None
        self.proc_output = None
        self.ref_from_runs = []
        self.id_selected_before_help = ""
        self.git_repo_for_diff = None
        self.git_diff = ""
        self.conan_base_proc = None

        #Thread event
        self.wait_check_github = None

        self.conan_base_regex = f"shred_conan_base\/(\d+\.\d+\.\d+)"

    def main_loop(self, astdscr):
        witch_init(astdscr)
        add_text_color("refname", curses.COLOR_YELLOW)
        add_text_color("path", curses.COLOR_CYAN)
        add_text_color("success", curses.COLOR_GREEN)
        add_text_color("fail", curses.COLOR_RED)
        input_buffer_save = 0

        frame_count = 0
        fps = [0.] * 10
        start = 0
        end = 1

        while self.running:
            fps[frame_count % 10] = 1.0 / (end - start)
            real_fps = accumulate(fps)
            for i in real_fps:
                real_fps = i / 10
            start = perf_counter()
            frame_count += 1
            start_frame()

            if is_key_pressed('?'):
                self.id_selected_before_help = selected_id()
                self.show_help = True

            start_layout("base", HORIZONTAL, Percentage(100) - 1)

            workspace_id = start_panel("Workspaces", Percentage(20), Percentage(100), start_selected=True)
            for ws in self.workspaces:
                hovered_ws, pressed = text_item(ws.path.name)
                if pressed:
                    if ws in self.workspace_opened:
                        self.workspace_opened.remove(ws)
                    else:
                        self.workspace_opened.add(ws)
                if hovered_ws and is_key_pressed("C"):
                    self.install_workspace(ws)


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
                                        self.ref_from_runs = []
                                        self.selected_ref_with_editable = (ref, root_editable, ws)
                                        self.hovered_root = None
                                for ref in root_editable.required_external_lib:
                                    conflict = ws.path in ref.conflicts and len(ref.conflicts[ws.path]) > 0
                                    symbol = " " if not conflict else ""
                                    _, pressed = text_item((f"  {symbol} {ref.ref}", "fail" if conflict else "refname"))

                                    if pressed:
                                        self.ref_from_runs = []
                                        self.selected_ref_with_editable = (ref, root_editable, ws)
                                        self.hovered_root = None
            end_panel()

            if self.install_proc and not self.hovered_root and self.proc_output:
                if self.install_proc.poll():
                    # finish reading proc and prepare to live if necessary
                    for line in self.install_proc.stdout.readline():
                        if line:
                            self.proc_output += line
                else:
                    line = self.install_proc.stdout.readline()
                    if line:
                        self.proc_output += line
                text_buffer(f"Installing", Percentage(80), Percentage(100), self.proc_output)
            else:
                # Cleanup data from install process
                self.install_proc = None
                self.proc_output = None

                if self.hovered_root:
                    # Cleanup cache data from other screens
                    self.ref_from_runs = []

                    ref, ws = self.hovered_root
                    root_editable = self.get_editable_from_ref(ref)

                    editables = [root_editable]
                    for ref in root_editable.required_local_lib:
                        editables.append(self.get_editable_from_ref(ref))

                    root_check_id = start_panel(f"{ref.package.name} check", Percentage(80) if not self.git_repo_for_diff else Percentage(39), Percentage(100))

                    self.git_repo_for_diff = None

                    for ed in editables:
                        if ed and ed.is_local:
                            ahead = 0
                            behind = 0

                            text_item([(f"{ed.package.name}", "refname"), " at ", (f"{ed.conan_path.parents[1]}", "path")])

                            ed.check_repo_dirty()
                            if ed.is_repo_dirty:
                                git_hovered_temp, _ = text_item([(" ", "fail"), (f"Repo is dirty ({ed.repo.active_branch})")])
                                if git_hovered_temp:
                                    self.git_repo_for_diff = ed.repo

                                # Detect external dirtyness
                                # Cmake submodule is dirty
                                ed.check_external_status()
                                if ed.cmake_status:
                                    text_item(ed.cmake_status)
                                # Workflows are not up to date
                                # Conan base is not up to date
                            else:
                                ed.update_rev_list()
                                rev_matches = ed.rev_list
                                rev_string = ""

                                if rev_matches:
                                    ahead = rev_matches.group(1)
                                    behind = rev_matches.group(2)
                                
                                    if int(ahead) != 0 or int(behind) != 0:
                                        rev_string = f" ↑{ahead}↓{behind} from origin/develop"

                                text_item([(" ", "success"), (f"Repo is clean ({ed.repo.active_branch})"), rev_string])
                                if ed.current_run and ed.current_run.status == "completed":
                                    if ed.current_run.conclusion == "success":
                                        text_item([(" ", "success"), (f"CI success for {ed.repo.active_branch}")])
                                    else:
                                        text_item([(" ", "fail"), (f"CI failure for {ed.repo.active_branch}")])
                                if ed.current_run and ed.current_run.status == "in_progress":
                                    text_item("CI in progress")

                            ed.update_conan_base_version()
                            if ed.conan_base_version and ed.conan_base_version < self.conan_base_newest_version:
                                text_item([(" ", "fail"), (f"shred_conan_base is not up to date (local={ed.conan_base_version}, adnn={self.conan_base_newest_version})")])
                            else:
                                text_item([(" ", "success"), (f"shred_conan_base is up to date")])

                            for req in ed.required_local_lib:
                                req.print_check_tui(ws.path)
                            for req in ed.required_external_lib:
                                req.print_check_tui(ws.path)

                            text_item("")
                    end_panel()

                    if self.git_diff != "":
                        text_buffer('Git diff', Percentage(41), Percentage(100), self.git_diff)

                    if self.git_repo_for_diff and self.git_diff == "":
                        self.git_diff = self.git_repo_for_diff.git.diff()
                    elif self.git_repo_for_diff is None:
                        self.git_diff = ""

                    if root_check_id == selected_id() and is_key_pressed(KEY_ESCAPE):
                        set_selected_id(workspace_id)

                elif self.selected_ref_with_editable:
                    selected_ref, selected_editable, ws = self.selected_ref_with_editable
                    if selected_editable:
                        ref = selected_editable.get_dependency_from_package(selected_ref.package)
                        selected_ref_editable = self.get_editable_from_ref(ref)
                        start_layout("ref_panel_and_log", VERTICAL, Percentage(80))
                        start_panel(f"{selected_ref.ref} conflict resolution", Percentage(100), Percentage(80), start_selected=True)

                        if len(selected_ref.conflicts[ws.path]) > 0:

                            text_item("Choose a version to resolve the conflict (press enter to select)", selectable=False)
                            text_item(f"In {selected_editable.package} at {selected_editable.conan_path}", selectable=False)
                            self.resolve_conflict_item(ref, ws)
                            for conflict in selected_ref.conflicts[ws.path]:
                                if isinstance(conflict, Workspace):
                                    text_item(f"In {conflict.path.name}", selectable=False)
                                    conflict_ref = conflict.get_dependency_from_package(selected_ref.package)
                                    self.resolve_conflict_item(conflict_ref, ws)
                                else:
                                    conflict_editable = self.get_editable_from_ref(selected_editable.get_dependency_from_package(conflict))
                                    if conflict_editable:
                                        conflict_ref = conflict_editable.get_dependency_from_package(selected_ref.package)
                                        text_item(f"In {conflict_editable.package} at {conflict_editable.conan_path.resolve()}", selectable=False)
                                        self.resolve_conflict_item(conflict_ref, ws)
                            if selected_ref_editable and selected_ref_editable.is_local:
                                text_item("", selectable=False)

                        if selected_ref_editable and selected_ref_editable.is_local:
                            runs_to_convert_to_ref = [run for run in selected_ref_editable.runs_develop[0:10] if run.status == "completed" and run.conclusion == "success"]
                            if len(self.ref_from_runs) != len(runs_to_convert_to_ref):
                                for run in runs_to_convert_to_ref:
                                    conflict_ref = ConanRef(f"{selected_ref.package.name}/{run.head_sha[0:10]}@{selected_ref.user}/{selected_ref.channel}")
                                    if conflict_ref not in self.ref_from_runs:
                                        self.ref_from_runs.append(conflict_ref)

                            if len(self.ref_from_runs) > 0:
                                text_item("Deployed recipe on conan", selectable=False)
                                for conflict_ref in self.ref_from_runs:
                                        self.resolve_conflict_item(conflict_ref, ws)

                        end_panel()
                        if is_key_pressed(KEY_ESCAPE):
                            self.selected_ref = None
                            set_selected_id(workspace_id)
                        start_panel("Workspace log", Percentage(100), Percentage(20))
                        for log in self.conflict_log:
                            text_item(log)
                        end_panel()
                        end_layout()
                else:
                    start_panel(f"Root check", Percentage(80), Percentage(100))
                    end_panel()

            end_layout()

            # TODO: status about github client

            if is_key_pressed("r"):
                self.load_stuff_and_shit()

            start_status_bar('test')
            if self.github_rate:
                text_item(f" FPS: {real_fps}, Github rate limit: {self.github_rate.limit - self.github_rate.remaining}/{self.github_rate.limit}", 30)
                text_item(f" ? Shows help, Tab to switch panel, Enter to open workspace, Enter to open root, Enter to open dependency", Percentage(100) - 31)
            end_status_bar()

            if self.show_help:
                id = start_floating_panel("Help", POSITION_CENTER, Percentage(50), Percentage(80))
                #self.print_help_line("C", "Conan workspace install hovered workspace")
                #self.print_help_line("d", "Cleanup workspace")
                self.print_help_line("Enter", "Opens workspace, root and dependency")
                self.print_help_line("Tab", "Switch panel selected")
                self.print_help_line("Esc/q", "Quits help or app")
                self.print_help_line("r", "Refresh panel")
                end_floating_panel()
                set_selected_id(id)
                if is_key_pressed("q") or is_key_pressed(KEY_ESCAPE):
                    set_selected_id(self.id_selected_before_help)
                    self.show_help = False
            elif is_key_pressed("q") or is_key_pressed(KEY_ESCAPE):
                raise SystemExit()

            end_frame()

            if self.conan_base_proc:
                if self.conan_base_proc.poll():
                    for line in self.conan_base_proc.stdout.readline():
                        if line:
                            self.process_conan_base_version_string(line)
                    self.conan_base_proc = None
                else:
                    line = self.conan_base_proc.stdout.readline()
                    self.process_conan_base_version_string(line)

            end = perf_counter()

    def process_conan_base_version_string(self, line):
        conan_base_match = re.search(self.conan_base_regex, line)
        if conan_base_match:
            match_semver = Semver(conan_base_match.group(1))

            if self.conan_base_newest_version is None:
                self.conan_base_newest_version = match_semver

            if self.conan_base_newest_version < match_semver:
                self.conan_base_newest_version = match_semver


    def resolve_conflict_item(self, conflict_ref, ws):
            _, pressed = text_item(f"  {conflict_ref} - {conflict_ref.date}")
            if pressed:
                self.resolve_conflict(self.editable_list, conflict_ref, ws)
            conflict_ref.fill_date_from_github(self.get_editable_from_ref(conflict_ref), self.thread_pool)

    def log_editable_conflict_resolution(self, editable, conflict_ref):
        self.conflict_log.append([f"Switched {conflict_ref.package.name} to ", (conflict_ref.version, "success"), f" in {editable.package.name}"])

    def log_workspace_conflict_resolution(self, conflict_ref, workspace):
        self.conflict_log.append([f"Switched {conflict_ref.package.name} to ", (conflict_ref.version, "success"), f" in {workspace.path.name}"])

    def resolve_conflict(self, editable_list, selected_conflict_ref, workspace):
        for editable in editable_list:
            if workspace.get_dependency_from_package(editable.package):
                version_changed = editable.change_version(selected_conflict_ref)
                if version_changed:
                    self.log_editable_conflict_resolution(editable, selected_conflict_ref)

        version_changed = workspace.change_version(selected_conflict_ref)
        if version_changed:
            self.log_workspace_conflict_resolution(selected_conflict_ref, workspace)

        compute_conflicts(self.workspaces, self.editable_list)

    def install_workspace(self, workspace):
        # FIX: This needs to be configurable
        self.proc_output = ""
        conan = shutil.which("conan")
        if conan:
            self.install_proc = subprocess.Popen(
                    [conan, "workspace", "install", "--profile", "game", "--build=missing", workspace.path.resolve()],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", cwd="/home/franz/gamedev/build")
        else:
            # TODO: should display a message that we can't find conan
            pass

    def print_help_line(self, shortcut, help_text):
        start_same_line()
        text_item((shortcut, "path"), 10)
        text_item(help_text)
        end_same_line()

    def run_ui(self):
        os.environ.setdefault('ESCDELAY', '25')
        curses.wrapper(self.main_loop)

    def load_stuff_and_shit(self):
        self.workspaces = [Workspace(Path(self.workspace_dir) / Path(x)) for x in os.listdir(self.workspace_dir) if "yml" in x]
        self.editable_list = create_editable_from_workspace_list(self.workspaces, self.gh_client, self.thread_pool)
        compute_conflicts(self.workspaces, self.editable_list)
        self.thread_pool.submit(self.check_github_rate)
        self.load_last_conan_base_version()

    def check_github_rate(self):
        while self.running:
            self.wait_check_github = threading.Event()
            self.github_rate = self.gh_client.get_rate_limit().core
            self.wait_check_github.wait(timeout=10.)

    def load_last_conan_base_version(self):
        conan = shutil.which("conan")
        # FIX: this needs to be configurable
        if conan and self.conan_base_newest_version is None:
            self.conan_base_proc = subprocess.Popen(
                    [conan, "search", "-r", "adnn", "shred_conan_base"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8")
        else:
            pass

    def get_editable_from_ref(self, conan_ref) -> Optional[Editable]:
        try:
            return next(e for e in self.editable_list if e.package == conan_ref.package)
        except StopIteration:
            return None

@click.command()
@click.option("--github-token", "-gt")
@click.argument("workspace_dir")
def tui(github_token, workspace_dir):
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
        runner.running = False
        if runner.wait_check_github:
            runner.wait_check_github.set()
        work.cancel()
        print("Waiting for queries to process")
        while not work.done():
            pass
