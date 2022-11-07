import os
import cursor
from pathlib import Path

import click
from github import BadCredentialsException, Github, GithubException, TwoFactorException
import py_cui

from sph.config import configCreate, configSaveToken
from sph.conflict import Conflict
from sph.conflicts_menu import ConflictsMenu
from sph.workspace import Workspace
from sph.editable import create_editable_from_workspace

# |---------------------------------------------------------|
# |Ws sel  | Root selection                                 |
# |        |                                                |
# |        |------------------------------------------------|
# |        |Root      | Dependency repository info          |
# |        |Reposit   |                                     |
# |        |----------|-------------------------------------|
# |        |Depend    |conflict resolution                  |
# |        |list      |                                     |
# |        |          |                                     |
# |        |          |                                     |
# |        |          |                                     |
# |        |          |                                     |
# |        |          |                                     |
# |        |          |                                     |
# |        |          |                                     |
# |---------------------------------------------------------|
#
# Transitions:
# - Workspace select
#   - set selected_workspace
#   - refresh Root selection
#   - remove root selected
#   - remove dependecy selected
# - Workspace unselect
#   - remove selected_workspace
#   - remove Root selected
#   - remove dependecy selected
# - Root select
#   - select root
#   - remove selected dependency
# - Root unselect
#   - remove Root selected
#   - remove dependecy selected
# - Dependency Select
#   - select dependency
# - Dependency Unselect
#   - remove dependecy selected


class WorkspaceItem:
    def __init__(self, workspace):
        self.workspace = workspace
        self.is_selected = False
    
    def __str__(self):
        return f"{'* ' if self.is_selected else '  '} {self.workspace.path.name}"

class RootItem:
    def __init__(self, conan_ref, conan_path):
        self.conan_ref = conan_ref
        self.conan_path = conan_path
        self.is_selected = False

    def __str__(self):
        return f"{'* ' if self.is_selected else '  '}{self.conan_ref.conan_ref} at ({self.conan_path.resolve().parents[0]}){' not present locally' if not self.conan_ref.is_local else ''}"

class DependencyItem:
    def __init__(self, conan_ref, local):
        self.conan_ref = conan_ref
        self.is_selected = False
        self.is_local = local

    def __str__(self):
        if self.is_selected:
            return f"  S {self.conan_ref.package.name}{' has conflicts' if len(self.conan_ref.conflicts) > 0 else ''}"
        if self.is_local:
            return f"  L {self.conan_ref.package.name}{' has conflicts' if len(self.conan_ref.conflicts) > 0 else ''}"
        return f"  X {self.conan_ref.conan_ref}{' has conflicts' if len(self.conan_ref.conflicts) > 0 else ''}"

class GitInfo:
    def __init__(self, editable):
        self.editable = editable

    def __str__(self):
        if self.editable.repo:
            return ' Git is clean' if not self.editable.repo.is_dirty() else ' Git is dirty'
        return ''

class GithubInfo:
    def __init__(self, editable):
        self.editable = editable

    def __str__(self):
        if self.editable.gh_repo is not None:
            if self.editable.gh_repo is not False:
                return ' Github is ready'
            else:
                return ' No repo on github'
        else:
            return 'Waiting for github repo'

        return ''

class WorkflowInfo:
    def __init__(self, editable):
        self.editable = editable

    def __str__(self):
        if self.editable.current_run is not None:
            if not self.editable.current_run:
                return 'No CI'
            if self.editable.current_run.status == 'in_progress':
                return 'CI in progress'
            if self.editable.current_run.status == 'completed':
                if self.editable.current_run.conclusion == 'success':
                    return ' CI success'
                else:
                    return ' CI failed'
        else:
            return 'Waiting for CI status'

        return ''

class WorkspaceTUI:

    def __init__(self, master, workspace_dir, gh_client):
        self.workflow_msg = ''
        self.gh_client = gh_client
        self.master = master
        self.master.toggle_unicode_borders()
        self.workspace_selected_index = -1

        self.workspaces = [WorkspaceItem(Workspace(Path(workspace_dir) / Path(x))) for x in os.listdir(workspace_dir) if "yml" in x]
        self.workspaces[0].is_hovered = True

        self.editable_list = []

        self.ws_menu = self.master.add_scroll_menu('Workspaces', 0, 0, row_span=16, column_span=3);
        self.ws_menu.add_key_command(py_cui.keys.KEY_ENTER, self.select_workspace)
        self.ws_menu.add_text_color_rule('', py_cui.WHITE_ON_BLACK, rule_type="contains", selected_color=py_cui.GREEN_ON_BLACK)
        self.ws_menu.add_item_list(self.workspaces)

        self.root_list = self.master.add_scroll_menu('Roots', 0, 3, row_span=2, column_span=13)
        self.root_list.add_key_command(py_cui.keys.KEY_BACKSPACE, self.return_to_ws)
        self.root_list.add_key_command(py_cui.keys.KEY_ENTER, self.select_root)
        self.root_list.add_text_color_rule('^  [^\s]*', py_cui.YELLOW_ON_BLACK, 'contains', match_type="regex")
        self.root_list.add_text_color_rule('^\* [^\s]*', py_cui.GREEN_ON_BLACK, 'contains', match_type="regex")

        self.root_info = self.master.add_scroll_menu('Root info', 2, 3, row_span=2, column_span=3)
        self.root_info.set_selectable(False)
        self.root_info.add_text_color_rule('', py_cui.RED_ON_BLACK, rule_type="contains")
        self.root_info.add_text_color_rule('', py_cui.GREEN_ON_BLACK, rule_type="contains")

        self.root_tree = self.master.add_scroll_menu('Dependency tree', 4, 3, row_span=12, column_span=3)
        self.root_tree.add_text_color_rule('L ', py_cui.YELLOW_ON_BLACK, rule_type="startswith")
        self.root_tree.add_text_color_rule('X ', py_cui.CYAN_ON_BLACK, rule_type="startswith")
        self.root_tree.add_text_color_rule('S ', py_cui.GREEN_ON_BLACK, rule_type="startswith")
        self.root_tree.add_key_command(py_cui.keys.KEY_ENTER, self.select_dependency)
        self.root_tree.add_key_command(py_cui.keys.KEY_UP_ARROW, self.avoid_select_root)
        self.root_tree.add_key_command(py_cui.keys.KEY_BACKSPACE, self.return_to_roots)
        self.root_tree.add_key_command(py_cui.keys.get_ascii_from_char('?'), self.show_root_tree_help)

        self.dep_repo_info = self.master.add_scroll_menu(f'Dependency repo info', 2, 6, row_span=2, column_span=10)
        self.dep_repo_info.set_selectable(False)
        self.dep_repo_info.add_text_color_rule('', py_cui.RED_ON_BLACK, rule_type="contains")
        self.dep_repo_info.add_text_color_rule('', py_cui.GREEN_ON_BLACK, rule_type="contains")

        self.dep_info = self.master.add_custom_widget(ConflictsMenu, f'Conflict resolution', 4, 6, row_span=12, column_span=10, padx=0, pady=0)
        self.dep_info.add_key_command(py_cui.keys.KEY_BACKSPACE, self.return_root_tree)
        self.dep_info.add_text_color_rule('', py_cui.WHITE_ON_BLACK, selected_color=py_cui.CYAN_ON_BLACK, rule_type="contains")

        self.master.move_focus(self.ws_menu)

    def show_root_tree_help(self):
        menu =self.master.show_menu_popup('Dependency tree help',
                                    [
                                        'Enter     select dependency',
                                        'c         commit root repo'
                                    ], lambda x: None)

    def select_workspace(self):
        self.root_list.clear()

        for w in self.ws_menu.get_item_list():
            w.is_selected = False

        item: WorkspaceItem = self.ws_menu.get()
        item.is_selected = True

        self.workspace = item.workspace
        self.editable_list = create_editable_from_workspace(item.workspace, self.gh_client)
        self.compute_conflicts(item.workspace)
        self.root_list.add_item_list([RootItem(ref, path) for (ref, path) in item.workspace.local_refs if ref.conan_ref in [x.conan_ref for x in item.workspace.root]])
        self.master.move_focus(self.root_list)

    def return_to_ws(self):
        self.root_list.clear()
        self.master.move_focus(self.ws_menu)

    def select_root(self):
        item = self.root_list.get()

        if item.conan_ref.is_local:
            item.is_selected = True
            self.create_local_root_data(item)
        else:
            self.create_non_local_root_data(item)

    def return_to_roots(self):
        self.master.move_focus(self.root_list)
        self.root_tree.clear()
        self.root_info.clear()

    def select_dependency(self):
        for d in self.root_tree.get_item_list():
            if isinstance(d, DependencyItem):
                    d.is_selected = False

        dependency = self.root_tree.get()
        dependency.is_selected = True

        self.dep_repo_info.set_title(f'{dependency.conan_ref.conan_ref} repo info')

        self.dependency_editable = self.get_editable_from_ref(dependency.conan_ref)
        if self.dependency_editable:
            repo_item_list = [
                    GitInfo(self.dependency_editable),
                    GithubInfo(self.dependency_editable),
                    WorkflowInfo(self.dependency_editable)
                    ]
            self.dep_repo_info.add_item_list(repo_item_list)


        self.dep_info.set_title(f'{dependency.conan_ref.conan_ref} info')

        item_list = []
        item_list += self.create_dep_item_list(dependency)

        self.dep_info.add_item_list(item_list)
        self.master.move_focus(self.dep_info)

    def return_root_tree(self):
        self.master.move_focus(self.root_tree)
        self.dep_repo_info.clear()
        self.dep_info.clear()

    def create_local_root_data(self, root):
        self.current_editable = [e for e in self.editable_list if e.package is root.conan_ref.package][0]
        self.root_info.add_item_list([
            GitInfo(self.current_editable),
            GithubInfo(self.current_editable),
            WorkflowInfo(self.current_editable)])

        item_list = [self.current_editable.package.name]

        for dep in self.current_editable.required_local_lib:
            item_list.append(DependencyItem(dep, True))

        for dep in self.current_editable.required_external_lib:
            item_list.append(DependencyItem(dep, False))


        self.root_tree.add_item_list(item_list)
        self.root_tree.set_selected_item_index(1)
        self.root_tree.set_help_text('Enter to select dependency - C to commit')
        self.master.move_focus(self.root_tree)

    def avoid_select_root(self):
        # Hack to avoid selecting the Root
        if self.root_tree.get_selected_item_index() == 1:
            self.root_tree.set_selected_item_index(2)

    def create_dep_item_list(self, dependency):
        if len(dependency.conan_ref.conflicts) == 0:
            return []

        ref = self.current_editable.get_dependency_from_package(dependency.conan_ref.package)
        base_list = [
            "Choose a version to resolve conflict (press enter to select)",
            f'In {self.current_editable.package} at {self.current_editable.conan_path.resolve()}:',
            Conflict(ref, self.get_editable_from_ref(ref))
        ]
        for conflict in dependency.conan_ref.conflicts:
            if isinstance(conflict, Workspace):
                ref = conflict.get_dependency_from_package(dependency.conan_ref.package)
                base_list += [
                        f'In {conflict.path.name}:',
                        Conflict(ref, self.get_editable_from_ref(ref))
                ]
            else:
                editable = self.get_editable_from_ref(self.current_editable.get_dependency_from_package(conflict))
                ref = editable.get_dependency_from_package(dependency.conan_ref.package)
                base_list += [
                    f'In {editable.package} at {editable.conan_path.resolve()}:',
                    Conflict(ref, self.get_editable_from_ref(ref))
                ]

        return base_list 

    def display_editable_info(self, f):
        list = self.dep_repo_info.get_item_list()

        for i, m in enumerate(list):
            if m == self.editable_github_info:
                if f.result() == True:
                    list[i] = ' Github is ready'
                    self.workflow_msg = 'Waiting for CI status'
                    list.append(self.workflow_msg)
                    self.dependency_editable.check_workflow(self.set_workflow_status(self.dep_repo_info))
                if f.result() == False:
                    list[i] = ' Github is not ready'
                
        self.dep_repo_info.clear()
        self.dep_repo_info.add_item_list(list)


    def create_non_local_root_data(self, root):
        self.dep_info.add_item_list([f"No git repo for {root.conan_ref.conan_ref}"])

    def get_editable_from_ref(self, conan_ref):
        filtered_editable = [e for e in self.editable_list if e.package == conan_ref.package]

        if len(filtered_editable) == 1:
            return filtered_editable[0]

    def compute_conflicts(self, workspace):
        editable_version_by_name = dict()

        for ref, _ in workspace.local_refs:
            if ref.package.name not in editable_version_by_name:
                editable_version_by_name[ref.package.name] = dict()

            if ref.conan_ref not in editable_version_by_name[ref.package.name]:
                editable_version_by_name[ref.package.name][ref.conan_ref] = set()

            editable_version_by_name[ref.package.name][ref.conan_ref].add(workspace)



        for e in self.editable_list:
            for ref in e.required_local_lib:
                if ref.package.name not in editable_version_by_name:
                    editable_version_by_name[ref.package.name] = dict()

                if ref.conan_ref not in editable_version_by_name[ref.package.name]:
                    editable_version_by_name[ref.package.name][ref.conan_ref] = set()

                editable_version_by_name[ref.package.name][ref.conan_ref].add(e.package)

            for ref in e.required_external_lib:
                if ref.package.name not in editable_version_by_name:
                    editable_version_by_name[ref.package.name] = dict()

                if ref.conan_ref not in editable_version_by_name[ref.package.name]:
                    editable_version_by_name[ref.package.name][ref.conan_ref] = set()

                editable_version_by_name[ref.package.name][ref.conan_ref].add(e.package)

        for e in self.editable_list:
            for req in e.required_local_lib:
                for ref_needed, value in editable_version_by_name[req.package.name].items():
                    if (e.package not in value) and (ref_needed is not req.conan_ref):
                        req.conflicts.update(value)

            for req in e.required_external_lib:
                for ref_needed, value in editable_version_by_name[req.package.name].items():
                    if (e.package not in value) and (ref_needed is not req.conan_ref):
                        req.conflicts.update(value)
                                            


@click.command()
@click.option("--github-token", "-gt")
@click.argument("workspace_dir")
def tui(github_token, workspace_dir):
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

    root = py_cui.PyCUI(16, 16)
    root.set_title('Conan workspace manager')
    root.set_refresh_timeout(1)

    WorkspaceTUI(root, workspace_dir, github_client)

    root.start()
    cursor.hide()
