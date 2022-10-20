import click

from sph.check import check
from sph.editable import create_editable_from_workspace
from sph.workflow import workflow_group
from sph.cleanup import cleanup

@click.group()
def be_helpful():
    pass

be_helpful.add_command(cleanup)
be_helpful.add_command(workflow_group)
be_helpful.add_command(check)
