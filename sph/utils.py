import configparser
import ast
import shutil
import os
import re
from pathlib import Path

import yaml

def get_editables_from_ws(ws_file):
    """
    Returns the editables from a workspace file path 
    :return: the editables or -1 if the file does not exists
    """
    if not ws_file.exists():
        raise FileNotFoundError(f"Workspace file {ws_file} does not exist.")
        return -1

    with open(ws_file, "r", encoding="utf-8") as file:
        workspace_data = yaml.safe_load(file)

    return workspace_data.get("editables", {})



def get_default_config_path():
    """ Get default config path"""
    xdg_config_home = os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
    if not os.path.exists(Path(xdg_config_home) / "sph"):
        os.makedirs("sph", exist_ok=True)
    return Path(xdg_config_home) / "sph" / "config.ini"


def ensure_workspace_directory(ws_dir):
    """
    Checks if the directory ws_dir exists.
    Creates if it does not and ask for deletion/creation if it does

    :param str ws_dir: the directory path
    """
    if os.path.exists(ws_dir):
        response = (
            input(
                f"The directory '{ws_dir}' already exists. "
                "Do you want to delete and recreate it? (y/N): "
            )
            .strip()
            .lower()
        )
        if response == "y":
            shutil.rmtree(ws_dir)
            os.makedirs(ws_dir)
        else:
            print(f"Using existing directory: {ws_dir}")
    else:
        os.makedirs(ws_dir)


def load_config(config_file):
    """ Loads the config"""
    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        config.read(config_file)
    return config


def set_env_vars(config_section):
    """ sets the env variable from the config section"""
    for key, value in config_section.items():
        os.environ[key.upper()] = value

def change_version(conanfile_path, package_name, new_reference, old_reference=None):
    text = None
    newtext = None
    regex = r""
    if old_reference is None:
        # matches a conan string reference of new_dependency
        # but does not match new_dependency/conan
        regex = r"{}\/(?!conan)[\w\.]+(@[\w]+\/[\w]+(#[\w])?)?".format(
            re.escape(package_name)
        )
    else:
        regex = re.escape(old_reference)

    with open(conanfile_path, "r", newline="", encoding="utf-8") as conanfile:
        text = conanfile.read()
        newtext = re.sub(regex, new_reference, text)
    with open(
        conanfile_path, "w", newline="", encoding="utf-8"
    ) as resolvedfile:
        resolvedfile.write(newtext)

    if newtext != text:
        print(
            f"Replaced {old_reference} by {new_reference} in {conanfile_path}"
        )
        return True

    return False


def extract_references_from_conanfile(conanfile_path):
    all_required_conan_ref = []
    with open(conanfile_path, "r", encoding="utf-8") as conanfile:
        conanfile_ast = ast.parse(conanfile.read())
        for node in ast.iter_child_nodes(conanfile_ast):
            if isinstance(node, ast.ClassDef):
                for class_node in ast.iter_child_nodes(node):
                    if isinstance(class_node, ast.Assign):
                        for target in class_node.targets:
                            if target.id == "requires":
                                all_required_conan_ref = [
                                    elt.value for elt in class_node.value.elts
                                ]
    return all_required_conan_ref


def split_reference_info(ref):
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
    raise ValueError(f"{ref} is not a conan ref")
