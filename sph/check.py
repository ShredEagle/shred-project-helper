import time

import click
from colorama import Fore
from halo import Halo
from github import (BadCredentialsException, Github, GithubException,
                    TwoFactorException)

from sph.workspace import Workspace
from sph.config import configCreate, configSaveToken
from sph.editable import create_editable_from_workspace_list


@click.command()
@click.option("--github-token", "-gt")
@click.argument("workspace")
def check(github_token, workspace):

    github_client = None;

    config, config_path = configCreate()

    if github_token:
        configSaveToken(config, config_path, github_token)

    github_token = config['github']['access_token']

    try:
        if not github_token:
            github_username = click.prompt('Github username')
            github_password = click.prompt('Github password')
            github_client = Github(github_username, github_password)
        else:
            github_client = Github(github_token)

        user = github_client.get_user()
        Halo(f'Logged in github as {user.login}').succeed()
    except BadCredentialsException as e:
        click.echo('Wrong github credentials')
        click.echo(e)
        raise click.Abort()
    except TwoFactorException as e:
        click.echo(
            'Can\'t use credentials for account with 2FA. Please use an' +
            ' access token.'
        )
        click.echo(e)
        raise click.Abort()
    except GithubException as e:
        click.echo('Github issue')
        click.echo(e)
        raise click.Abort()

    # Get dependency tree
    workspace_data = Workspace(workspace)
    waiting = Halo("Waiting for github")
    waiting.start()
    editables = create_editable_from_workspace_list([workspace_data], github_client)
    waiting.succeed()

    click.echo()

    editable_version_by_name = dict()

    for ref, path in workspace_data.local_refs:
        if ref.package.name not in editable_version_by_name:
            editable_version_by_name[ref.package.name] = dict()

        if ref.ref not in editable_version_by_name[ref.package.name]:
            editable_version_by_name[ref.package.name][ref.ref] = set()

        editable_version_by_name[ref.package.name][ref.ref].add("workspace")



    for e in editables:
        for ref in e.required_local_lib:
            if ref.package.name not in editable_version_by_name:
                editable_version_by_name[ref.package.name] = dict()

            if ref.ref not in editable_version_by_name[ref.package.name]:
                editable_version_by_name[ref.package.name][ref.ref] = set()

            editable_version_by_name[ref.package.name][ref.ref].add(e.package)

        for ref in e.required_external_lib:
            if ref.package.name not in editable_version_by_name:
                editable_version_by_name[ref.package.name] = dict()

            if ref.ref not in editable_version_by_name[ref.package.name]:
                editable_version_by_name[ref.package.name][ref.ref] = set()

            editable_version_by_name[ref.package.name][ref.ref].add(e.package)

    for e in editables:
        for req in e.required_local_lib:
            for ref_needed, value in editable_version_by_name[req.package.name].items():
                if (e.package not in value) and (ref_needed is not req.ref):
                    req.conflicts.update(value)

        for req in e.required_external_lib:
            for ref_needed, value in editable_version_by_name[req.package.name].items():
                if (e.package not in value) and (ref_needed is not req.ref):
                    req.conflicts.update(value)

    for e in editables:
        click.echo(f"{Fore.CYAN}{e.package.name}{Fore.RESET} at {Fore.YELLOW}{e.conan_path.parents[1]}{Fore.RESET}")
        if e.repo.is_dirty():
            Halo("Repo is dirty").fail()
        else:
            Halo("Repo is clean").succeed()
            ci_status = Halo("Waiting for CI")
            ci_status.start()
            e.checking_workflow_task()
            if e.current_run.status == "completed":
                if e.current_run.conclusion == "success":
                    ci_status.succeed("CI success")
                else:
                    ci_status.fail("CI failure")
            if e.current_run.status == "in_progress":
                pass
        if len(e.required_local_lib) + len(e.required_external_lib) == 0:
            Halo("No dependency").succeed()
        for req in e.required_local_lib:
            req.print_check(1)
        for req in e.required_external_lib:
            req.print_check(1)
        click.echo()

    # Create a list of all dependencies and their version
    # Check version of non local dependencies
    # Give list of version for non local dependencies with conflict
    # Check dirtiness of local dependencies
    # Check workflow state of local dependencies

