import typing
from dataclasses import dataclass
from pathlib import Path

import click
import yaml

from sph.editable import ConanRefDescriptor

Workspace = typing.NewType('Workspace', None)

@dataclass
class Workspace:
    root: ConanRefDescriptor
    editables = []
    path: Path
    data = None
    folder_path: Path

    def __init__(self, workspace):

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

        self.root = ConanRefDescriptor(self.data["root"])

        for name, path in self.data["editables"].items():
            self.editables.append((ConanRefDescriptor(name), self.folder_path / Path(path["path"])))

    def __str__(self):
        ret = f"{self.path}:\n"
        for (e, p) in self.editables:
            ret += str(e)
        return ret
