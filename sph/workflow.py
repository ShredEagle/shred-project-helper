# Allows to bump all reusable workflows versions

import click
import re, os


regex_read = "uses: (shredeagle/reusable-workflows)/\.github/workflows/(?P<workflow>.+\.yml)@(?P<version>.+)"
regex_substitute = "@.+"


def substitute_version(file, new_version):
    with open(file, "r+") as f:
        outlines = []
        for line in f.readlines():
            if re.search(regex_read, line):
                line = re.sub(regex_substitute, "@{}".format(new_version), line)
            outlines.append(line)
        f.seek(0)
        f.truncate(0)
        f.writelines(outlines)


def print_version(file):
    with open(file) as f:
        for line in f.readlines():
            m = re.search(regex_read, line)
            if m:
                print("{}:\tWorkflow {} is version {}".format(os.path.basename(file), m["workflow"], m["version"]))


def walk_workflows(repo, callback, *args):
    workflows_folder = os.path.join(repo, ".github/workflows")
    if not os.path.exists(workflows_folder):
        click.echo("Cannot find workflows folder in {}.".format(os.getcwd()))
        raise click.Abort()
    for file in os.listdir(workflows_folder):
        file = os.path.join(workflows_folder, file)
        if file.endswith(".yml"):
            callback(file, *args)


@click.command(name = "setv")
@click.argument("version")
@click.option("--repo", default = ".", help = "The repository containings workflows.")
def set_workflow_version(version, repo):
    walk_workflows(repo, substitute_version, version)


@click.command(name = "list")
@click.option("--repo", default = ".", help = "The repository containings workflows.")
def get_workflow_version(repo):
    walk_workflows(repo, print_version)


@click.group(name = "workflow")
def workflow_group():
    pass


workflow_group.add_command(get_workflow_version)
workflow_group.add_command(set_workflow_version)
