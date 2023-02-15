from sph.workspace import Workspace
class ConanContext:
    """
    Represent the whole conan context.
    Contains the workspace, all the conan ref present in the workspace
    and there associated editable
    """
    def __init__(self, workspace_path_list):
        self.workspace_list = []
        for workspace_path in workspace_path_list:
            self.workspace_list.append(Workspace(workspace_path))

        self.conan_refs = []

        for conan_ref in self.conan_refs:
            for workspace in self.workspace_list:
        self.conflicts
