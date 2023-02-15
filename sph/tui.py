import asyncio
import curses
import functools
import os
import re
import shutil
import signal
import subprocess
import threading
from itertools import accumulate
from pathlib import Path
from time import perf_counter
from typing import Optional

import click
from github import BadCredentialsException, Github, GithubException, TwoFactorException
from ratelimit import limits

from sph.conan_ref import ConanRef
from sph.config import configCreate, configSaveToken
from sph.conflict import compute_conflicts
from sph.editable import Editable, create_editable_from_workspace_list
from sph.loop import Loop
from sph.semver import Semver
from sph.workspace import Workspace
import witchtui

KEY_ESCAPE = chr(27)


class Runner:
    def __init__(self, workspace_dir, gh_client, loop):
        # debug variables
        self.frame_count = 0
        self.fps = [0.0] * 10
        self.start = 0
        self.end = 1

        self.loop = loop
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

        # Thread event
        self.wait_check_github = None

        self.conan_base_regex = r"shred_conan_base\/(\d+\.\d+\.\d+)"

    async def main_loop(self):
        self.fps[self.frame_count % 10] = 1.0 / (self.end - self.start)
        real_fps = accumulate(self.fps)
        for i in real_fps:
            real_fps = i / 10
        self.start = perf_counter()
        self.frame_count += 1
        witchtui.start_frame()

        if witchtui.is_key_pressed("?"):
            self.id_selected_before_help = witchtui.selected_id()
            self.show_help = True

        witchtui.start_layout("base", witchtui.HORIZONTAL, witchtui.Percentage(100) - 1)

        workspace_id = witchtui.start_panel(
            "Left sidebar", witchtui.Percentage(20), witchtui.Percentage(100), start_selected=True
        )

        for ws in self.workspaces:
            ws_opened = witchtui.tree_node(ws.path.name)
            if witchtui.is_item_hovered() and witchtui.is_key_pressed("C"):
                self.install_workspace(ws)
            if ws_opened:
                for ref, _ in [
                    (ref, path)
                    for ref, path in ws.local_refs
                    if ref.ref in [x.ref for x in ws.root]
                ]:
                    root_editable = self.get_editable_from_ref(ref)
                    if not root_editable:
                        witchtui.text_item([(f"  {ref.ref} not loaded", "refname")])
                        continue
                    if not root_editable.is_local:
                        witchtui.text_item([(f"  {ref.ref} not local", "refname")])
                        continue

                    ref_opened = witchtui.tree_node([(f"  {ref.ref}", "refname")])
                    self.hovered_root = (
                        (ref, ws) if witchtui.is_item_hovered() else self.hovered_root
                    )

                    if ref_opened:
                        for ref in root_editable.required_local_lib:
                            conflict = (
                                ws.path in ref.conflicts
                                and len(ref.conflicts[ws.path]) > 0
                            )
                            symbol = " " if not conflict else ""
                            if witchtui.text_item(
                                (
                                    f"  {symbol} {ref.ref}",
                                    "fail" if conflict else "path",
                                )
                            ):
                                self.ref_from_runs = []
                                self.selected_ref_with_editable = (
                                    ref,
                                    root_editable,
                                    ws,
                                )
                                self.hovered_root = None
                        for ref in root_editable.required_external_lib:
                            conflict = (
                                ws.path in ref.conflicts
                                and len(ref.conflicts[ws.path]) > 0
                            )
                            symbol = " " if not conflict else ""

                            if witchtui.text_item(
                                (
                                    f"  {symbol} {ref.ref}",
                                    "fail" if conflict else "refname",
                                )
                            ):
                                self.ref_from_runs = []
                                self.selected_ref_with_editable = (
                                    ref,
                                    root_editable,
                                    ws,
                                )
                                self.hovered_root = None
        witchtui.end_panel()

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
            witchtui.text_buffer(
                f"Installing", witchtui.Percentage(80), witchtui.Percentage(100), self.proc_output
            )
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

                root_check_id = witchtui.start_panel(
                    f"{ref.package.name} check",
                    witchtui.Percentage(80) if not self.git_repo_for_diff else witchtui.Percentage(39),
                    witchtui.Percentage(100),
                )

                self.git_repo_for_diff = None

                for ed in editables:
                    if ed and ed.is_local:
                        ahead = 0
                        behind = 0

                        witchtui.text_item(
                            [
                                (f"{ed.package.name}", "refname"),
                                " at ",
                                (f"{ed.conan_path.parents[1]}", "path"),
                            ]
                        )

                        self.loop.run_safe_in_executor(
                            None,
                            ed.check_workflow,
                        )
                        self.loop.run_safe_in_executor(None, ed.check_repo_dirty)
                        if ed.is_repo_dirty:
                            witchtui.text_item(
                                [
                                    (" ", "fail"),
                                    (f"Repo is dirty ({ed.repo.active_branch})"),
                                ]
                            )
                            if witchtui.is_item_hovered():
                                self.git_repo_for_diff = ed.repo

                            # Detect external dirtyness
                            # Cmake submodule is dirty
                            self.loop.run_safe_in_executor(
                                None,
                                ed.check_external_status,
                            )
                            if ed.cmake_status:
                                witchtui.text_item(ed.cmake_status)
                            # Workflows are not up to date
                            # Conan base is not up to date
                        else:
                            self.loop.run_safe_in_executor(None, ed.update_rev_list)
                            rev_matches = ed.rev_list
                            rev_string = ""

                            if rev_matches:
                                ahead = rev_matches.group(1)
                                behind = rev_matches.group(2)

                                if int(ahead) != 0 or int(behind) != 0:
                                    rev_string = (
                                        f" ↑{ahead}↓{behind} from origin/develop"
                                    )

                            witchtui.text_item(
                                [
                                    (" ", "success"),
                                    (f"Repo is clean ({ed.repo.active_branch})"),
                                    rev_string,
                                ]
                            )
                            if ed.current_run and ed.current_run.status == "completed":
                                if ed.current_run.conclusion == "success":
                                    witchtui.text_item(
                                        [
                                            (" ", "success"),
                                            (f"CI success for {ed.repo.active_branch}"),
                                        ]
                                    )
                                else:
                                    witchtui.text_item(
                                        [
                                            (" ", "fail"),
                                            (f"CI failure for {ed.repo.active_branch}"),
                                        ]
                                    )
                            if (
                                ed.current_run
                                and ed.current_run.status == "in_progress"
                            ):
                                witchtui.text_item("CI in progress")

                        ed.update_conan_base_version()
                        if self.conan_base_newest_version is None or (
                            ed.conan_base_version
                            and ed.conan_base_version < self.conan_base_newest_version
                        ):
                            witchtui.text_item(
                                [
                                    (" ", "fail"),
                                    (
                                        f"shred_conan_base is not up to date (local={ed.conan_base_version}, adnn={self.conan_base_newest_version})"
                                    ),
                                ]
                            )
                        else:
                            witchtui.text_item(
                                [
                                    (" ", "success"),
                                    (f"shred_conan_base is up to date"),
                                ]
                            )

                        for req in ed.required_local_lib:
                            req.print_check_tui(
                                ws.path, self.get_editable_from_ref(req)
                            )
                        for req in ed.required_external_lib:
                            req.print_check_tui(ws.path)

                        witchtui.text_item("")
                witchtui.end_panel()

                if self.git_diff != "":
                    witchtui.text_buffer(
                        "Git diff", witchtui.Percentage(41) + 1, witchtui.Percentage(100), self.git_diff
                    )

                if self.git_repo_for_diff and self.git_diff == "":
                    self.git_diff = self.git_repo_for_diff.git.diff()
                elif self.git_repo_for_diff is None:
                    self.git_diff = ""

                if root_check_id == witchtui.selected_id() and witchtui.is_key_pressed(KEY_ESCAPE):
                    witchtui.set_selected_id(workspace_id)

            elif self.selected_ref_with_editable:
                (
                    selected_ref,
                    selected_editable,
                    ws,
                ) = self.selected_ref_with_editable
                if selected_editable:
                    ref = selected_editable.get_dependency_from_package(
                        selected_ref.package
                    )
                    selected_ref_editable = self.get_editable_from_ref(ref)
                    witchtui.start_layout("ref_panel_and_log", witchtui.VERTICAL, witchtui.Percentage(80))
                    conflict_panel_id = witchtui.start_panel(
                        f"{selected_ref.ref} conflict resolution",
                        witchtui.Percentage(100),
                        witchtui.Percentage(80),
                        start_selected=True,
                    )

                    if len(selected_ref.conflicts[ws.path]) > 0:
                        witchtui.text_item(
                            "Choose a version to resolve the conflict (press enter to select)",
                            selectable=False,
                        )
                        witchtui.text_item(
                            f"In {selected_editable.package} at {selected_editable.conan_path}",
                            selectable=False,
                        )
                        self.resolve_conflict_item(ref, ws)
                        for conflict in selected_ref.conflicts[ws.path]:
                            if isinstance(conflict, Workspace):
                                witchtui.text_item(f"In {conflict.path.name}", selectable=False)
                                conflict_ref = conflict.get_dependency_from_package(
                                    selected_ref.package
                                )
                                self.resolve_conflict_item(conflict_ref, ws)
                            else:
                                conflict_editable = self.get_editable_from_ref(
                                    selected_editable.get_dependency_from_package(
                                        conflict
                                    )
                                )
                                if conflict_editable:
                                    conflict_ref = (
                                        conflict_editable.get_dependency_from_package(
                                            selected_ref.package
                                        )
                                    )
                                    witchtui.text_item(
                                        f"In {conflict_editable.package} at {conflict_editable.conan_path.resolve()}",
                                        selectable=False,
                                    )
                                    self.resolve_conflict_item(conflict_ref, ws)
                        if selected_ref_editable and selected_ref_editable.is_local:
                            witchtui.text_item("", selectable=False)

                    if selected_ref_editable and selected_ref_editable.is_local:
                        runs_to_convert_to_ref = [
                            run
                            for run in selected_ref_editable.runs_develop[0:10]
                            if run.status == "completed" and run.conclusion == "success"
                        ]
                        if len(self.ref_from_runs) != len(runs_to_convert_to_ref):
                            for run in runs_to_convert_to_ref:
                                conflict_ref = ConanRef(
                                    f"{selected_ref.package.name}/{run.head_sha[0:10]}@{selected_ref.user}/{selected_ref.channel}"
                                )
                                if conflict_ref not in self.ref_from_runs:
                                    self.ref_from_runs.append(conflict_ref)

                        if len(self.ref_from_runs) > 0:
                            witchtui.text_item("Deployed recipe on conan", selectable=False)
                            for conflict_ref in self.ref_from_runs:
                                self.resolve_conflict_item(conflict_ref, ws)

                    witchtui.end_panel()

                    if conflict_panel_id == witchtui.selected_id() and witchtui.is_key_pressed(
                        KEY_ESCAPE
                    ):
                        witchtui.set_selected_id(workspace_id)

                    witchtui.start_panel("Workspace log", witchtui.Percentage(100), witchtui.Percentage(20))
                    for log in self.conflict_log:
                        witchtui.text_item(log)
                    witchtui.end_panel()
                    witchtui.end_layout()
            else:
                witchtui.start_panel(f"Root check", witchtui.Percentage(80), witchtui.Percentage(100))
                witchtui.end_panel()

        witchtui.end_layout()

        # TODO: status about github client

        if witchtui.is_key_pressed("r"):
            self.loop.run_safe_in_executor(None, self.load_editables)

        witchtui.start_status_bar("test")
        if self.github_rate:
            witchtui.text_item(
                f" FPS: {real_fps:4.2f}, Github rate limit: {self.github_rate.limit - self.github_rate.remaining}/{self.github_rate.limit}",
                50,
            )
            witchtui.text_item(
                f" ? Shows help, Tab to switch panel, Enter to open workspace, Enter to open root, Enter to open dependency",
                witchtui.Percentage(100) - 51,
            )
        witchtui.end_status_bar()

        if self.show_help:
            id = witchtui.start_floating_panel(
                "Help", POSITION_CENTER, witchtui.Percentage(50), witchtui.Percentage(80)
            )
            # self.print_help_line("C", "Conan workspace install hovered workspace")
            # self.print_help_line("d", "Cleanup workspace")
            self.print_help_line("Enter", "Opens workspace, root and dependency")
            self.print_help_line("Tab", "Switch panel selected")
            self.print_help_line("Esc/q", "Quits help or app")
            self.print_help_line("r", "Refresh panel")
            witchtui.end_floating_panel()
            witchtui.set_selected_id(id)
            if witchtui.is_key_pressed("q") or witchtui.is_key_pressed(KEY_ESCAPE):
                witchtui.set_selected_id(self.id_selected_before_help)
                self.show_help = False
        elif witchtui.is_key_pressed("q") or witchtui.is_key_pressed(KEY_ESCAPE):
            raise SystemExit()

        witchtui.end_frame()

        if self.conan_base_proc:
            if self.conan_base_proc.poll():
                for line in self.conan_base_proc.stdout.readline():
                    if line:
                        self.process_conan_base_version_string(line)
                self.conan_base_proc = None
            else:
                line = self.conan_base_proc.stdout.readline()
                self.process_conan_base_version_string(line)

        self.end = perf_counter()

    async def run_loop(self, astdscr):
        witchtui.witch_init(astdscr)
        witchtui.add_text_color("refname", curses.COLOR_YELLOW)
        witchtui.add_text_color("path", curses.COLOR_CYAN)
        witchtui.add_text_color("success", curses.COLOR_GREEN)
        witchtui.add_text_color("fail", curses.COLOR_RED)
        self.loop.run_safe_in_executor(None, self.load_editables)
        self.loop.run_safe_in_executor(None, self.load_last_conan_base_version)

        while self.running:
            self.loop.run_safe_in_executor(None, self.check_github_rate)
            await self.main_loop()
            await asyncio.sleep(0)

    def process_conan_base_version_string(self, line):
        conan_base_match = re.search(self.conan_base_regex, line)
        if conan_base_match:
            match_semver = Semver(conan_base_match.group(1))

            if self.conan_base_newest_version is None:
                self.conan_base_newest_version = match_semver

            if self.conan_base_newest_version < match_semver:
                self.conan_base_newest_version = match_semver

    def resolve_conflict_item(self, conflict_ref, ws):
        if witchtui.text_item(f"  {conflict_ref} - {conflict_ref.date}"):
            self.resolve_conflict(self.editable_list, conflict_ref, ws)

        self.loop.run_safe_in_executor(
            None,
            functools.partial(
                conflict_ref.fill_date_from_github,
                self.get_editable_from_ref(conflict_ref),
            ),
        )

    def log_editable_conflict_resolution(self, editable, conflict_ref):
        self.conflict_log.append(
            [
                f"Switched {conflict_ref.package.name} to ",
                (conflict_ref.version, "success"),
                f" in {editable.package.name}",
            ]
        )

    def log_workspace_conflict_resolution(self, conflict_ref, workspace):
        self.conflict_log.append(
            [
                f"Switched {conflict_ref.package.name} to ",
                (conflict_ref.version, "success"),
                f" in {workspace.path.name}",
            ]
        )

    def resolve_conflict(self, editable_list, selected_conflict_ref, workspace):
        for editable in editable_list:
            if workspace.get_dependency_from_package(editable.package):
                version_changed = editable.change_version(selected_conflict_ref)
                if version_changed:
                    self.log_editable_conflict_resolution(
                        editable, selected_conflict_ref
                    )

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
                [
                    conan,
                    "workspace",
                    "install",
                    "--profile",
                    "game",
                    "--build=missing",
                    workspace.path.resolve(),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                cwd="/home/franz/gamedev/build",
            )
        else:
            # TODO: should display a message that we can't find conan
            pass

    def print_help_line(self, shortcut, help_text):
        witchtui.start_same_line()
        witchtui.text_item((shortcut, "path"), 10)
        witchtui.text_item(help_text)
        witchtui.end_same_line()

    def load_editables(self):
        self.workspaces = [
            Workspace(Path(self.workspace_dir) / Path(x))
            for x in os.listdir(self.workspace_dir)
            if "yml" in x
        ]
        self.editable_list = create_editable_from_workspace_list(
            self.workspaces, self.gh_client
        )
        compute_conflicts(self.workspaces, self.editable_list)

    @limits(calls=1, period=10, raise_on_limit=False)
    def check_github_rate(self):
        self.github_rate = self.gh_client.get_rate_limit().core

    def load_last_conan_base_version(self):
        conan = shutil.which("conan")
        # FIX: this needs to be configurable
        if conan and self.conan_base_newest_version is None:
            self.conan_base_proc = subprocess.Popen(
                [conan, "search", "-r", "adnn", "shred_conan_base"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
            )
        else:
            pass

    def get_editable_from_ref(self, conan_ref) -> Optional[Editable]:
        try:
            return next(e for e in self.editable_list if e.package == conan_ref.package)
        except StopIteration:
            return None


def stop_loop():
    for task in asyncio.all_tasks():
        task.cancel()


def main_tui(github_client, workspace_dir, stdscr):
    loop = Loop()
    loop.loop.add_signal_handler(signal.SIGTERM, stop_loop)
    runner = Runner(workspace_dir, github_client, loop)

    try:
        tui_future = loop.loop.run_until_complete(runner.run_loop(stdscr))
        tui_future.result()
    except asyncio.CancelledError:
        print("Loop got cancelled")
    except (KeyboardInterrupt, SystemExit):
        runner.running = False


@click.command()
@click.option("--github-token", "-gt")
@click.argument("workspace_dir")
def tui(github_token, workspace_dir):
    github_client = None

    config, config_path = configCreate()

    if github_token:
        configSaveToken(config, config_path, github_token)

    github_token = config["github"]["access_token"]

    try:
        if not github_token:
            github_username = click.prompt("Github username")
            github_password = click.prompt("Github password")
            github_client = Github(github_username, github_password)
        else:
            github_client = Github(github_token)
    except BadCredentialsException:
        click.echo("Wrong github credentials")
        raise click.Abort()
    except TwoFactorException:
        click.echo(
            "Can't use credentials for account with 2FA. Please use an"
            + " access token."
        )
        raise click.Abort()
    except GithubException:
        click.echo("Github issue")
        raise click.Abort()

    # screen_temp = curses.initscr()
    # curses.noecho()
    # screen_temp.keypad(True)
    # curses.cbreak()

    # main_tui(github_client, workspace_dir, screen_temp)

    # curses.nocbreak()
    # screen_temp.keypad(False)
    # curses.echo()

    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(functools.partial(main_tui, github_client, workspace_dir))
