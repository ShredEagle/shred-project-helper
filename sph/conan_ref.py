import re
from github import GithubException

from halo import Halo
from colorama import Fore

from sph.conan_package import ConanPackage
from sph.utils import extract_info_from_conan_ref, t
from witchtui.widgets import text_item

class ConanRef:
    @property
    def ref(self):
        ref = f'{self.package.name}/{self.version}'

        if self.user:
            ref += f'@{self.user}/{self.channel}'

        if self.revision != "":
            ref += f'#{self.revision}'

        return ref

    def __init__(self, ref):
        name, version, user, channel, revision = extract_info_from_conan_ref(
                ref
            )
        self.package = ConanPackage(name)
        self.version = version
        self.user = user
        self.channel = channel
        self.revision = revision
        self.conflicts = dict()
        self.date = None
        self.has_local_editable = False

    def __eq__(self, other):
        return hasattr(other, 'ref') and self.ref == other.ref

    def __str__(self):
        return f'{self.ref}'
    
    def __hash__(self):
        return self.ref.__hash__()

    def fill_date_from_github(self, editable, thread_pool):
        if self.date is None:
            self.date = "Waiting for date"
            thread_pool.submit(self.fill_date_from_github_task(editable))

    def fill_date_from_github_task(self, editable):
        def task():
            match = re.search(r"/([\w]{10})", self.ref)

            if match:
                if editable.gh_repo is not None and editable.gh_repo is not False:
                    try:
                        commit = editable.gh_repo.get_commit(match.group(1)).commit
                        self.date = commit.author.date.strftime("%Y/%m/%d %H:%M:%S")
                    except GithubException:
                        self.date = f"No commit found for SHA {match.group(1)}"
        return task

    def print_check(self, workspace_path, level=0):
        if len(self.conflicts[workspace_path]) > 0:
            ret = f"{t(level)}{self.ref} conflicts with "
            for c in self.conflicts[workspace_path]:
                ret += f"{Fore.RED}{c}{Fore.RESET} "
            Halo(ret).fail()
        else:
            ret = f"{t(level)}{self.ref} is ok"
            Halo(ret).succeed()

    def print_check_tui(self, workspace_path):
        if workspace_path in self.conflicts and len(self.conflicts[workspace_path]) > 0:
            conflicts = ""
            for c in self.conflicts[workspace_path]:
                conflicts += f"{c} "
            text_item([(" ", "fail"), f"{self.ref} conflicts with ", (conflicts, "fail")])
        else:
            text_item([(" ", "success"), f"{self.ref} is ok"])
