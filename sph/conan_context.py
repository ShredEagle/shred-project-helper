import ast
import fileinput
import asyncio
import functools
import os
import re
import shutil
import subprocess
import threading
from inspect import isawaitable
from contextlib import suppress
from pathlib import Path

import aiohttp
from dateutil.parser import isoparse

from sph.conan_package import ConanPackage
from sph.conan_ref import ConanRef
from sph.editable import Editable
from sph.errors import EditableNotInFilesystem, NoEditableException
from sph.semver import Semver
from sph.workspace import Workspace

GITHUB_REPO_WORKFLOW_RUN_URL = "https://api.github.com/repos/{owner}/{repo}/actions/runs?per_page={per_page}&status={status}&branch={branch}&conclusion={conclusion}&head_sha={head_sha}"

GITHUB_RATE_URL = "https://api.github.com/rate_limit"

GITHUB_SAFETY_FACTOR = 0.8


class Default(dict):
    def __missing__(self, key):
        return ""


class GithubRunStub:
    def __init__(self, status, conclusion, head_sha, date):
        self.status = status
        self.conclusion = conclusion
        self.head_sha = head_sha
        self.date = date


class ConanContext:
    """Contains all the data in the list of workspace"""

    def __init__(self, workspace_dir, github_token):
        self.github_token = github_token
        self.workspace_list = [
            Workspace(Path(workspace_dir) / Path(x))
            for x in os.listdir(workspace_dir)
            if "yml" in x
        ]

        self.package_dict = {}
        self.create_package_set()
        if (len(self.package_dict) == 0):
            raise NoEditableException("There is no editable so there is nothing to do")

        for workspace in self.workspace_list:
            for conan_ref in workspace.conan_ref_list:
                if conan_ref.package.name in self.package_dict:
                    package = self.package_dict[conan_ref.package.name]
                    conan_ref.package = package

        self.compute_conflicts()

        self.context_running = True
        self.context_loop = asyncio.new_event_loop()
        self.context_queue =  asyncio.Queue()
        threading.Thread(target=self.run_threaded_loop).start()

        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.github_rate_limit = 0
        self.github_rate_remaining = 0
        self.conan_base_newest_version = None
        self.conan_base_regex = r"shred_conan_base\/(\d+\.\d+\.\d+)"
        self.error_log = []
        
        self.cleanup = False
        self.cleanup_path_to_delete = []

    @property
    def editable_list(self):
        """Retrieves the editable list from the package_set"""
        return [package.editable for package in self.package_dict.values()]

    def retrieve_build_folder_list(self, workspace):
        self.cleanup = True
        self.context_queue.put_nowait(self.build_folder_list_task(workspace))

    async def build_folder_list_task(self, workspace):
        root_folder = workspace.path.parents[0]
        with fileinput.input(
            (root_folder / workspace.layout_filename).resolve()
        ) as f:
            for line in f:
                if line == '[build_folder]\n':
                    build_folder = Path(f.readline())
                    build_location = build_folder.parents[1]

        for path in workspace.editable_path_list:
            path_to_delete = (
                    root_folder / path / build_location
            ).resolve()
            self.cleanup_path_to_delete.append((path_to_delete, os.path.isdir(path_to_delete)))

    def stop_context(self):
        """Stops the async tasks in the context_loop"""
        for task in asyncio.all_tasks(self.context_loop):
            task.cancel()

    def run_threaded_loop(self):
        """Starts the loop that retrieve asynchronous data (should be called in a thread)"""
        asyncio.set_event_loop(self.context_loop)
        try:
            asyncio.ensure_future(self.data_fetch_loop(), loop=self.context_loop)
            asyncio.ensure_future(self.remote_data_fetch_loop(), loop=self.context_loop)
            asyncio.ensure_future(self.process_queue(), loop=self.context_loop)
            self.context_loop.run_until_complete(
                asyncio.gather(*asyncio.all_tasks(self.context_loop))
            )
        except asyncio.CancelledError:
            pending = asyncio.all_tasks(self.context_loop)
            with suppress(asyncio.CancelledError):
                self.context_loop.run_until_complete(asyncio.gather(*pending, self.context_queue.join()))

    async def process_queue(self):
        while True:
            task = await self.context_queue.get()
            if isawaitable(task):
                await task
            else:
                raise TypeError("Context queue can only process awaitable")
            self.context_queue.task_done()

    async def data_fetch_loop(self):
        while True:
            await asyncio.gather(
                *self.check_all_cmake_submodule(),
                *self.update_all_rev_list(),
                *self.check_all_repo_dirtyness(),
            )
            await asyncio.sleep(1)

    async def remote_data_fetch_loop(self):
        while True:
            await asyncio.gather(
                self.get_workflow_run_information(),
                self.check_github_rate(),
                self.call_conan_search_conan_base(),
            )
            # Waits to consume the github api times the safety factor
            # in an hour which should be the expire time
            await asyncio.sleep(
                3600
                / (
                    self.github_rate_limit
                    * GITHUB_SAFETY_FACTOR
                    / (2 * len(self.editable_list))
                )
            )

    def get_all_local_editables(self):
        """Get all editables that are present on the filesystem"""
        return [
            package.editable
            for package in self.package_dict.values()
            if package.editable.is_in_filesystem
        ]

    def process_conan_base_version_string(self, line):
        conan_base_match = re.search(self.conan_base_regex, line)
        if conan_base_match:
            match_semver = Semver(conan_base_match.group(1))

            if self.conan_base_newest_version is None:
                self.conan_base_newest_version = match_semver

            if self.conan_base_newest_version < match_semver:
                self.conan_base_newest_version = match_semver

            return True

        return False

    async def call_conan_search_conan_base(self):
        conan = shutil.which("conan")
        # FIX: this needs to be configurable
        if conan and self.conan_base_newest_version is None:
            output = subprocess.run(
                [conan, "search", "-r", "adnn", "shred_conan_base"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
            )
            for line in output.stdout.splitlines():
                if self.process_conan_base_version_string(line):
                    break

    def check_all_repo_dirtyness(self):
        futures = []
        for editable in self.get_all_local_editables():
            future = self.context_loop.create_future()
            self.context_loop.call_soon_threadsafe(
                functools.partial(editable.check_repo_dirty, future)
            )
            futures.append(future)

        return futures

    async def check_github_rate(self):
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(GITHUB_RATE_URL) as response:
                json_body = await response.json()
                self.github_rate_limit = json_body["resources"]["core"]["limit"]
                self.github_rate_remaining = json_body["resources"]["core"]["remaining"]

    def update_all_rev_list(self):
        """Check cmake submodule status for all editables"""
        futures = []
        for editable in self.get_all_local_editables():
            future = self.context_loop.create_future()
            self.context_loop.call_soon_threadsafe(
                functools.partial(editable.update_rev_list, future)
            )
            futures.append(future)

        return futures

    def check_all_cmake_submodule(self):
        """Check cmake submodule status for all editables"""
        futures = []
        for editable in self.get_all_local_editables():
            future = self.context_loop.create_future()
            self.context_loop.call_soon_threadsafe(
                functools.partial(editable.check_cmake_submodule, future)
            )
            futures.append(future)

        return futures

    async def get_workflow_run_information(self):
        for editable in self.get_all_local_editables():
            try:
                async with aiohttp.ClientSession(headers=self.headers) as session:
                    async with session.get(
                        GITHUB_REPO_WORKFLOW_RUN_URL.format_map(
                            Default(
                                owner=editable.github_owner,
                                repo=editable.github_repo,
                                per_page=20,
                                conclusion="success",
                                branch="develop",
                            )
                        )
                    ) as response:
                        json_body = await response.json()
                        for run in json_body["workflow_runs"][0:10]:
                            editable.succesful_develop_runs.append(
                                GithubRunStub(
                                    run["status"],
                                    run["conclusion"],
                                    run["head_sha"],
                                    isoparse(run["head_commit"]["timestamp"]),
                                )
                            )
                    async with session.get(
                        GITHUB_REPO_WORKFLOW_RUN_URL.format_map(
                            Default(
                                owner=editable.github_owner,
                                repo=editable.github_repo,
                                per_page=1,
                                status="completed",
                                head_sha=editable.repo.head.commit.hexsha,
                            )
                        )
                    ) as response:
                        json_body = await response.json()
                        if json_body["total_count"] > 0:
                            run = json_body["workflow_runs"][0]
                            editable.active_sha_run = GithubRunStub(
                                run["status"],
                                run["conclusion"],
                                run["head_sha"],
                                isoparse(run["head_commit"]["timestamp"]),
                            )
                        else:
                            editable.active_sha_run = False
            except aiohttp.ContentTypeError:
                self.error_log.append(
                    [("Json error: ", "fail"), "Cannot parse github json content\n"]
                )
            except aiohttp.ClientError:
                self.error_log.append(
                    [("Http error: ", "fail"), "Could not connect to github"]
                )

    def create_package_set(self):
        """Creates a list of editables from a list of workspace"""

        for workspace in self.workspace_list:
            for project_conan_path in workspace.editable_path_list:
                editable = Editable(project_conan_path)
                if not editable.is_in_filesystem:
                    raise EditableNotInFilesystem()
                package = editable.package
                if package.name not in self.package_dict:
                    self.package_dict[package.name] = package

        for editable in self.get_all_local_editables():
            self.create_editable_dependency(editable)

    def create_editable_dependency(self, editable):
        """Creates the conan ref list of dependency for `editable`"""
        all_required_conan_ref = []
        with open(editable.conan_path, "r", encoding="utf-8") as conanfile:
            conanfile_ast = ast.parse(conanfile.read())
            for node in ast.iter_child_nodes(conanfile_ast):
                if isinstance(node, ast.ClassDef):
                    for class_node in ast.iter_child_nodes(node):
                        if isinstance(class_node, ast.Assign):
                            for target in class_node.targets:
                                if target.id == "requires":
                                    all_required_conan_ref = [
                                        elt.value for elt in class_node.value.elts
                                    ]

        for dep in all_required_conan_ref:
            package_name = dep.split("/")[0]
            if package_name != editable.package.name:
                ref_is_local = package_name in self.package_dict
                if package_name in self.package_dict:
                    editable.required_conan_ref.append(
                        ConanRef(dep, package=self.package_dict[package_name])
                    )
                else:
                    editable.required_conan_ref.append(
                        ConanRef(dep, package=ConanPackage(package_name))
                    )

    def compute_conflicts(self):
        """Compute the conflicts between all the editables in editable_list and the workspace"""
        for workspace in self.workspace_list:
            editable_version_by_name = {}
            # TODO: I think this is wrong it should filter all the editable present on the filesystem
            editable_list_filtered = [
                package.editable
                for package in self.package_dict.values()
                if package.name
                in [ref.package.name for ref in workspace.conan_ref_list]
            ]
            for ref in workspace.conan_ref_list:
                ref.conflicts[workspace.path] = set()
                if ref.package.name not in editable_version_by_name:
                    editable_version_by_name[ref.package.name] = {}

                if ref.ref not in editable_version_by_name[ref.package.name]:
                    editable_version_by_name[ref.package.name][ref.ref] = set()

                editable_version_by_name[ref.package.name][ref.ref].add(workspace)

            for editable in editable_list_filtered:
                for ref in editable.required_conan_ref:
                    ref.conflicts[workspace.path] = set()
                    if ref.package.name not in editable_version_by_name:
                        editable_version_by_name[ref.package.name] = {}

                    if ref.ref not in editable_version_by_name[ref.package.name]:
                        editable_version_by_name[ref.package.name][ref.ref] = set()

                    editable_version_by_name[ref.package.name][ref.ref].add(
                        editable.package
                    )

            for editable in editable_list_filtered:
                for req in editable.required_conan_ref:
                    for ref_needed, value in editable_version_by_name[
                        req.package.name
                    ].items():
                        if (editable.package not in value) and (
                            ref_needed is not req.ref
                        ):
                            req.conflicts[workspace.path].update(value)

    # TODO: make this work
    def install_workspace(self, workspace):
        # FIX: This needs to be configurable
        proc_output = ""
        conan = shutil.which("conan")
        if conan:
            install_proc = subprocess.Popen(
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
