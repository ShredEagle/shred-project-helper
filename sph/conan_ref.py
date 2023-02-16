import re

from sph.conan_package import ConanPackage
from sph.errors import RegexpFormatException
from witchtui.widgets import text_item


class ConanRef:
    def __init__(self, ref, package=None, date=None):
        name, version, user, channel, revision = self.extract_info_from_conan_ref(ref)
        self.package = package if package else ConanPackage(name)
        self.version = version
        self.user = user
        self.channel = channel
        self.revision = revision
        self.conflicts = {}
        self._commit_date = date

    @property
    def has_local_editable(self):
        return self.package.editable and self.package.editable.is_in_filesystem

    @property
    def commit_date(self):
        if self._commit_date:
            return self._commit_date
        else:
            editable = self.package.editable
            if editable.is_in_filesystem:
                for run in editable.succesful_develop_runs:
                    if run.head_sha[0:10] == self.version:
                        self._commit_date = run.date.strftime("%Y/%m/%d %H:%M:%S")
                        return self._commit_date
                if len(editable.succesful_develop_runs) == 0:
                    return "Waiting for github runs..."
            else:
                return "Can't get date for non local editable"

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

        raise RegexpFormatException(
            f"Could not read {ref} with our current regexp please file a an"
            + "issue with the conan ref at https://github.com/ShredEagle/shred-project-helper/issues"
        )

    def __eq__(self, other):
        return hasattr(other, "ref") and self.ref == other.ref

    def __str__(self):
        return f"{self.ref}"

    def __hash__(self):
        return self.ref.__hash__()

    def print_check_tui(self, workspace_path, editable=None):
        if workspace_path in self.conflicts and len(self.conflicts[workspace_path]) > 0:
            conflicts = ""
            conflicts = " ".join(
                [str(conflict) for conflict in self.conflicts[workspace_path]]
            )
            text_item(
                [(" ", "fail"), f"{self.ref} conflicts with ", (conflicts, "fail")]
            )
        else:
            # if editable is not None and len(editable.runs_develop) > 0:
            #     last_run_ref_sha = editable.runs_develop[0].head_sha[0:10]
            #     if last_run_ref_sha != self.version:
            #         text_item(
            #             [
            #                 (" ", "refname"),
            #                 f"{self.ref} is ok but not last deployed version",
            #             ]
            #         )
            #         return
            text_item([(" ", "success"), f"{self.ref} is ok"])
