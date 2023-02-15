import re

from ratelimit import limits
from github import GithubException
from witchtui.widgets import text_item

from sph.conan_package import ConanPackage


class ConanRef:
    def __init__(self, ref):
        name, version, user, channel, revision = self.extract_info_from_conan_ref(ref)
        self.package = ConanPackage(name)
        self.version = version
        self.user = user
        self.channel = channel
        self.revision = revision
        self.conflicts = {}
        self.date = None
        self.has_local_editable = False

    @property
    def ref(self):
        ref = f"{self.package.name}/{self.version}"

        if self.user:
            ref += f"@{self.user}/{self.channel}"

        if self.revision != "":
            ref += f"#{self.revision}"

        return ref

    def extract_info_from_conan_ref(self, ref):
        match = re.search(r"([\w\.]+)\/([^@]+)(@(\w+)\/(\w+)#?(\w+)?)?", ref)
        if match:
            if len(match.groups()) == 3:
                return (match.group(1), match.group(2), "", "", "")
            if len(match.groups()) == 6:
                return (
                    match.group(1),
                    match.group(2),
                    match.group(4),
                    match.group(5),
                    "",
                )

            return (
                match.group(1),
                match.group(2),
                match.group(4),
                match.group(5),
                match.group(6),
            )

        raise Exception(
            f"Could not read {ref} with our current regexp please file a an" +
            "issue with the conan ref at https://github.com/ShredEagle/shred-project-helper/issues"
        )

    def __eq__(self, other):
        return hasattr(other, "ref") and self.ref == other.ref

    def __str__(self):
        return f"{self.ref}"

    def __hash__(self):
        return self.ref.__hash__()

    @limits(calls=10, period=10, raise_on_limit=False)
    def fill_date_from_github(self, editable):
        if self.date is None:
            self.date = "Waiting for date"
            match = re.search(r"/([\w]{10})", self.ref)

            if match:
                if editable.gh_repo is not None and editable.gh_repo is not False:
                    try:
                        commit = editable.gh_repo.get_commit(match.group(1)).commit
                        self.date = commit.author.date.strftime("%Y/%m/%d %H:%M:%S")
                    except GithubException:
                        self.date = f"No commit found for SHA {match.group(1)}"


    def print_check_tui(self, workspace_path, editable=None):
        if workspace_path in self.conflicts and len(self.conflicts[workspace_path]) > 0:
            conflicts = ""
            conflicts = str.join(self.conflicts[workspace_path], " ")
            text_item(
                [(" ", "fail"), f"{self.ref} conflicts with ", (conflicts, "fail")]
            )
        else:
            if editable is not None and len(editable.runs_develop) > 0:
                last_run_ref_sha = editable.runs_develop[0].head_sha[0:10]
                if last_run_ref_sha != self.version:
                    text_item(
                        [
                            (" ", "refname"),
                            f"{self.ref} is ok but not last deployed version",
                        ]
                    )
                    return
            text_item([(" ", "success"), f"{self.ref} is ok"])
