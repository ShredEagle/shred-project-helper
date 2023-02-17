import re
from pathlib import Path

import click
import yaml

from sph.conan_ref import ConanRef


class Workspace:
    def __init__(self, workspace):
        self.editable_path_list = []
        self.conan_ref_list = []
        self.path = Path(workspace)
        if not self.path.is_file():
            self.path = self.path / "workspace.yml"
        self.folder_path = self.path.parents[0]

        try:
            with open(self.path.resolve(), "r", encoding="utf-8") as workspace_file:
                try:
                    self.data = yaml.full_load(workspace_file)
                except yaml.YAMLError as exc:
                    click.echo(f"Can't parse file {self.path}")
                    click.echo(exc)
                    raise click.Abort()

        except OSError as exc:
            click.echo(f"Can't open file {self.path}")
            click.echo(exc)
            raise click.Abort()

        root_data = self.data["root"]
        if not isinstance(root_data, list):
            root_data = [root_data]

        self.layout_filename = self.data["layout"]

        self.root = [ConanRef(root) for root in root_data]

        for ref, path in self.data["editables"].items():
            self.conan_ref_list.append(ConanRef(ref))
            self.editable_path_list.append(
                self.folder_path / Path(path["path"])
            )

    def change_version(self, new_dependency, old_dependency=None):
        text = None
        newtext = None
        regex = r""
        if old_dependency is None:
            # matches a conan string reference of new_dependency
            # but does not match new_dependency/conan
            regex = r"{}\/(?!conan)[\w\.]+(@[\w]+\/[\w]+(#[\w])?)?".format(
                re.escape(new_dependency.package.name)
            )
        else:
            regex = re.escape(old_dependency)

        with open(self.path, "r", newline="") as conanfile:
            text = conanfile.read()
            newtext = re.sub(regex, new_dependency.ref, text)
        with open(self.path, "w", newline="") as resolvedfile:
            resolvedfile.write(newtext)

        if text != newtext:
            ref_to_change = next(
                x
                for x in self.conan_ref_list
                if x.package.name == new_dependency.package.name
            )
            ref_to_change.version = new_dependency.version
            ref_to_change.user = new_dependency.user
            ref_to_change.channel = new_dependency.channel
            ref_to_change.revision = new_dependency.revision
            return True

        return False

    def get_dependency_from_package(self, package):
        try:
            return next(filter(lambda x: x.package == package, self.conan_ref_list))
        except StopIteration:
            return None

    def __eq__(self, other):
        if isinstance(other, Workspace):
            return self.path == other.path
        return False

    def __str__(self):
        return self.path.name

    def __hash__(self):
        return self.path.__hash__()
