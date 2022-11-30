import click

from sph.check import check
from sph.workflow import workflow_group
from sph.cleanup import cleanup
from sph.tui import tui

@click.group()
def be_helpful():
    pass

be_helpful.add_command(cleanup)
be_helpful.add_command(workflow_group)
be_helpful.add_command(check)
be_helpful.add_command(tui)
