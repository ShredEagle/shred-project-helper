from pathlib import Path
from typing_extensions import Any

import click
import yaml

from sph.conan_ref import ConanRef

class Workspace:
    def __init__(self, workspace):

        self.local_refs = []
        self.path = Path(workspace)
        if not self.path.is_file():
            self.path = self.path / "workspace.yml"
        self.folder_path = self.path.parents[0]

        try:
            with open(self.path.resolve(), "r") as workspace_file:
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

        self.root = [ConanRef(root) for root in root_data]

        for ref, path in self.data["editables"].items():
            self.local_refs.append((ConanRef(ref), self.folder_path / Path(path["path"])))

    def get_dependency_from_package(self, package):
       return next(filter(lambda x: x[0].package == package, self.local_refs))[0]


    def __str__(self):
        return self.path.name

    def __hash__(self):
        return self.path.__hash__()
