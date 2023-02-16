import asyncio
import curses
from itertools import accumulate
from time import perf_counter
from typing import Optional

import witchtui
from sph.conan_ref import ConanRef
from sph.editable import Editable
from sph.workspace import Workspace

KEY_ESCAPE = chr(27)


class SphUi:
    def __init__(self, screen, context):
        witchtui.witch_init(screen)
        witchtui.add_text_color("refname", curses.COLOR_YELLOW)
        witchtui.add_text_color("path", curses.COLOR_CYAN)
        witchtui.add_text_color("success", curses.COLOR_GREEN)
        witchtui.add_text_color("fail", curses.COLOR_RED)

        # debug variables
        self.frame_count = 0
        self.fps = [0.0] * 10
        self.start = 0
        self.end = 1

        # UI state
        self.workspace_opened = set()
        self.root_opened = set()
        self.hovered_root = None
        self.show_help = False
        self.selected_ref_with_editable = None

        # UI data
        self.conflict_log = []
        self.context = context
        self.git_diff = ""
        self.git_repo_for_diff = None
        self.github_rate = None
        self.ref_from_runs = []

    def print_help_line(self, shortcut, help_text):
        witchtui.start_same_line()
        witchtui.text_item((shortcut, "path"), 10)
        witchtui.text_item(help_text)
        witchtui.end_same_line()

    def get_editable_from_ref(self, conan_ref, editable_list) -> Optional[Editable]:
        try:
            return next(e for e in editable_list if e.package == conan_ref.package)
        except StopIteration:
            return None

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

    def resolve_conflict_item(self, editable_list, conflict_ref, ws):
        if witchtui.text_item(f"  {conflict_ref} - {conflict_ref.commit_date}"):
            self.resolve_conflict(conflict_ref, ws)

    def resolve_conflict(self, selected_conflict_ref, workspace):
        editable_list = self.context.get_all_local_editables()
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

        self.context.compute_conflicts()

    def install_workspace(self, ws):
        pass

    async def draw(self):
        workspace_list = self.context.workspace_list
        editable_list = self.context.editable_list
        self.end = perf_counter()
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
            "Left sidebar",
            witchtui.Percentage(20),
            witchtui.Percentage(100),
            start_selected=True,
        )

        for ws in workspace_list:
            ws_opened = witchtui.tree_node(ws.path.name)
            if witchtui.is_item_hovered() and witchtui.is_key_pressed("C"):
                self.install_workspace(ws)
            if ws_opened:
                for ref in [
                    ref
                    for ref in ws.conan_ref_list
                    if ref.ref in [x.ref for x in ws.root]
                ]:
                    root_editable = self.get_editable_from_ref(ref, editable_list)
                    if not root_editable:
                        witchtui.text_item([(f"  {ref.ref} not loaded", "refname")])
                        continue
                    if not root_editable.is_in_filesystem:
                        witchtui.text_item([(f"  {ref.ref} not local", "refname")])
                        continue

                    ref_opened = witchtui.tree_node([(f"  {ref.ref}", "refname")])
                    self.hovered_root = (
                        (ref, ws) if witchtui.is_item_hovered() else self.hovered_root
                    )

                    if ref_opened:
                        for ref in root_editable.required_conan_ref:
                            conflict = (
                                ws.path in ref.conflicts
                                and len(ref.conflicts[ws.path]) > 0
                            )
                            symbol = " " if not conflict else ""
                            if witchtui.text_item(
                                (
                                    f"  {symbol} {ref.ref}",
                                    "fail"
                                    if conflict
                                    else "path"
                                    if ref.has_local_editable
                                    else "refname",
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

        # TODO: put this is context
        # if self.install_proc and not self.hovered_root and self.proc_output:
        #     if self.install_proc.poll():
        #         # finish reading proc and prepare to live if necessary
        #         for line in self.install_proc.stdout.readline():
        #             if line:
        #                 self.proc_output += line
        #     else:
        #         line = self.install_proc.stdout.readline()
        #         if line:
        #             self.proc_output += line
        #     witchtui.text_buffer(
        #         f"Installing",
        #         witchtui.Percentage(80),
        #         witchtui.Percentage(100),
        #         self.proc_output,
        #     )
        # Cleanup data from install process
        # self.install_proc = None
        # self.proc_output = None

        if self.hovered_root:
            # Cleanup cache data from other screens
            self.ref_from_runs = []

            ref, ws = self.hovered_root
            root_editable = self.get_editable_from_ref(ref, editable_list)

            editables = [root_editable]
            for ref in [
                local_ref
                for local_ref in root_editable.required_conan_ref
                if local_ref.has_local_editable
            ]:
                editables.append(self.get_editable_from_ref(ref, editable_list))

            root_check_id = witchtui.start_panel(
                f"{ref.package.name} check",
                witchtui.Percentage(80)
                if not self.git_repo_for_diff
                else witchtui.Percentage(39),
                witchtui.Percentage(100),
            )

            self.git_repo_for_diff = None

            for ed in [editable for editable in editables if editable.is_in_filesystem]:
                witchtui.text_item(
                    [
                        (f"{ed.package.name}", "refname"),
                        " at ",
                        (f"{ed.conan_path.parents[1]}", "path"),
                    ]
                )

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
                    if ed.cmake_status:
                        witchtui.text_item(ed.cmake_status)
                else:
                    rev_matches = ed.rev_list
                    rev_string = ""

                    if rev_matches:
                        ahead = rev_matches.group(1)
                        behind = rev_matches.group(2)

                        if int(ahead) != 0 or int(behind) != 0:
                            rev_string = f" ↑{ahead}↓{behind} from origin/develop"

                    witchtui.text_item(
                        [
                            (" ", "success"),
                            (f"Repo is clean ({ed.repo.active_branch})"),
                            rev_string,
                        ]
                    )
                    if ed.active_sha_run is None:
                        witchtui.text_item(
                            [
                                (f"  Getting CI status..."),
                            ]
                        )
                    elif not ed.active_sha_run:
                        witchtui.text_item(
                            [
                                (
                                    f"  No workflow run for active commit in branch {ed.repo.active_branch}"
                                ),
                            ]
                        )

                    if ed.active_sha_run and ed.active_sha_run.conclusion == "success":
                        witchtui.text_item(
                            [
                                (" ", "success"),
                                (f"CI success for {ed.repo.active_branch}"),
                            ]
                        )
                    elif (
                        ed.active_sha_run and ed.active_sha_run.conclusion == "failure"
                    ):
                        witchtui.text_item(
                            [
                                (" ", "fail"),
                                (f"CI failure for {ed.repo.active_branch}"),
                            ]
                        )
                    elif (
                        ed.active_sha_run and ed.active_sha_run.status == "in_progress"
                    ):
                        witchtui.text_item("  CI in progress")

                if self.context.conan_base_newest_version is None or (
                    ed.conan_base_version
                    and ed.conan_base_version < self.context.conan_base_newest_version
                ):
                    witchtui.text_item(
                        [
                            (" ", "fail"),
                            (
                                f"shred_conan_base is not up to date (local={ed.conan_base_version}, adnn={self.context.conan_base_newest_version})"
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

                for req in ed.required_conan_ref:
                    req.print_check_tui(
                        ws.path, self.get_editable_from_ref(req, editable_list)
                    )

                witchtui.text_item("")
            witchtui.end_panel()

            if self.git_diff != "":
                witchtui.text_buffer(
                    "Git diff",
                    witchtui.Percentage(41) + 1,
                    witchtui.Percentage(100),
                    self.git_diff,
                )

            if self.git_repo_for_diff and self.git_diff == "":
                self.git_diff = self.git_repo_for_diff.git.diff()
            elif self.git_repo_for_diff is None:
                self.git_diff = ""

            if root_check_id == witchtui.selected_id() and witchtui.is_key_pressed(
                KEY_ESCAPE
            ):
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
                selected_ref_editable = self.get_editable_from_ref(ref, editable_list)
                witchtui.start_layout(
                    "ref_panel_and_log", witchtui.VERTICAL, witchtui.Percentage(80)
                )
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
                    self.resolve_conflict_item(editable_list, ref, ws)
                    for conflict in selected_ref.conflicts[ws.path]:
                        if isinstance(conflict, Workspace):
                            witchtui.text_item(
                                f"In {conflict.path.name}", selectable=False
                            )
                            conflict_ref = conflict.get_dependency_from_package(
                                selected_ref.package
                            )
                            self.resolve_conflict_item(editable_list, conflict_ref, ws)
                        else:
                            conflict_editable = self.get_editable_from_ref(
                                selected_editable.get_dependency_from_package(conflict),
                                editable_list,
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
                                self.resolve_conflict_item(
                                    editable_list, conflict_ref, ws
                                )
                    if selected_ref_editable and selected_ref_editable.is_in_filesystem:
                        witchtui.text_item("", selectable=False)

                if selected_ref_editable and selected_ref_editable.is_in_filesystem:
                    runs_to_convert_to_ref = [
                        run
                        for run in selected_ref_editable.succesful_develop_runs[0:10]
                        if run.status == "completed" and run.conclusion == "success"
                    ]
                    if len(self.ref_from_runs) != len(runs_to_convert_to_ref):
                        for run in runs_to_convert_to_ref:
                            conflict_ref = ConanRef(
                                f"{selected_ref.package.name}/{run.head_sha[0:10]}@{selected_ref.user}/{selected_ref.channel}",
                                package=selected_ref.package,
                                date=run.date.strftime("%Y/%m/%d %H:%M:%S"),
                            )
                            if conflict_ref not in self.ref_from_runs:
                                self.ref_from_runs.append(conflict_ref)

                    witchtui.text_item("Deployed recipe on conan", selectable=False)
                    if len(self.ref_from_runs) > 0:
                        for conflict_ref in self.ref_from_runs:
                            self.resolve_conflict_item(editable_list, conflict_ref, ws)
                    else:
                        witchtui.text_item("Retrieving recipes from github...")

                witchtui.end_panel()

                if (
                    conflict_panel_id == witchtui.selected_id()
                    and witchtui.is_key_pressed(KEY_ESCAPE)
                ):
                    witchtui.set_selected_id(workspace_id)

                witchtui.start_panel(
                    "Workspace log",
                    witchtui.Percentage(100),
                    witchtui.Percentage(20),
                )
                for log in self.conflict_log:
                    witchtui.text_item(log)
                witchtui.end_panel()
                witchtui.end_layout()
        else:
            witchtui.start_panel(
                f"Root check", witchtui.Percentage(80), witchtui.Percentage(100)
            )
            witchtui.end_panel()

        witchtui.end_layout()

        # TODO: find a way to reload the package_dict from the context
        # if witchtui.is_key_pressed("r"):
        #     self.loop.run_safe_in_executor(None, self.load_editables)

        witchtui.start_status_bar("status_bar")
        witchtui.text_item(
            f" FPS: {real_fps:4.2f}, Github rate limit: {self.context.github_rate_limit - self.context.github_rate_remaining}/{self.context.github_rate_limit}",
            50,
        )
        witchtui.text_item(
            f" ? Shows help, Tab to switch panel, Enter to open workspace, Enter to open root, Enter to open dependency",
            witchtui.Percentage(100) - 51,
        )
        witchtui.end_status_bar()

        if self.show_help:
            id = witchtui.start_floating_panel(
                "Help",
                POSITION_CENTER,
                witchtui.Percentage(50),
                witchtui.Percentage(80),
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
        await asyncio.sleep(0.010)
