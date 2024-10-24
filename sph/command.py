import argparse
import json
import os
import re
import subprocess
import configparser
from pathlib import Path

import argcomplete

from .editable import EditableStore
from .utils import (
    ensure_workspace_directory,
    get_default_config_path,
    get_editables_from_ws,
    load_config,
    set_env_vars,
    change_version,
    extract_references_from_conanfile,
    split_reference_info
)


def get_conan_info_command_list(build_os, profile, root_repo, temp_file_path):
    command_list = [
        "conan",
        "info",
        "-pr:b",
        f"build/{build_os}",  # "build/Windows",
        "-pr:h",
        profile,
        Path(root_repo) / "conan" / "conanfile.py",
        "-j",
        temp_file_path,
    ]

    return command_list


def get_conan_workspace_install_command_list(
        root_repo, workspace, profile, build_os, multi=False
):
    command_list = [
        "conan",
        "workspace",
        "install",
        f"{'../' if not multi else ''}../{root_repo}/conan/workspaces/{workspace}.yml",
        "-pr:h",
        profile,
        "-pr:b",
        f"build/{build_os}",  # "build/Windows",
        "--build",
        "missing",
        "-o",
        "*:build_tests=True",
    ]
    return command_list


def get_cmake_command_list(root_repo, suffix, build_type=None):
    command_list = [
        "cmake",
        "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW",
    ]

    if build_type:
        command_list += [
            f"-DCMAKE_TOOLCHAIN_FILE=../../{root_repo}/"
            f"build-conan-{suffix}/{build_type}/generators/conan_toolchain.cmake",
            "-G",
            "Unix Makefiles",
            f"-DCMAKE_BUILD_TYPE={build_type}",
        ]
    else:
        command_list += [
            f"-DCMAKE_TOOLCHAIN_FILE=../{root_repo}/"
            f"build-conan-{suffix}/generators/conan_toolchain.cmake",
        ]

    command_list += [f"{'../' if build_type else ''}../{root_repo}/conan/workspaces"]

    return command_list


def install():
    root_repo = os.getenv("ROOTREPO")
    workspace = os.getenv("WORKSPACE")
    compiler = os.getenv("COMPILER")
    profile = os.getenv("PROFILE")
    suffix = os.getenv("SUFFIX")
    build_os = os.getenv("OS")

    if not Path(root_repo).exists():
        print(f"Not {root_repo} directory (probably wrong location to launch sph)")
        return

    ws_dir = f"ws_{root_repo}_{workspace}_{suffix}"
    ensure_workspace_directory(ws_dir)

    os.chdir(ws_dir)

    if compiler in ["gcc", "clang"]:
        # Run Clang commands
        os.makedirs("Release", exist_ok=True)
        os.chdir("Release")
        subprocess.run(
            get_conan_workspace_install_command_list(
                root_repo, workspace, profile, build_os
            ),
            check=False,
        )
        subprocess.run(
            get_cmake_command_list(root_repo, suffix, "Release"), check=False
        )
        os.chdir("..")

        os.makedirs("Debug", exist_ok=True)
        os.chdir("Debug")
        subprocess.run(
            get_conan_workspace_install_command_list(
                root_repo, workspace, f"{profile}-dev", build_os
            ),
            check=False,
        )
        subprocess.run(
            get_cmake_command_list(root_repo, suffix, "Debug"), check=False
        )
        os.chdir("..")
    else:
        # Run Visual Studio commands
        subprocess.run(
            get_conan_workspace_install_command_list(
                root_repo, workspace, profile, build_os, True
            ),
            check=False,
        )
        subprocess.run(
            get_conan_workspace_install_command_list(
                root_repo, workspace, f"{profile}-dev", build_os, True
            ),
            check=False,
        )
        subprocess.run(get_cmake_command_list(root_repo, suffix), check=False)


def setup(config_file):
    config = load_config(config_file)
    compiler = ["clang16", "gcc14.0", "Visual Studio17"]
    profile = input("Profile name: ")
    config[profile] = {
        "ROOTREPO": input("Enter root repo (default: snacman): ") or "snacman",
        "WORKSPACE": (
            input("Enter workspace (default: complete): ") or "complete"
        ),
        "PROFILE": input("Conan Profile (default: game): ") or "game",
    }
    conan_profile = configparser.ConfigParser(
        delimiters=("="), allow_no_value=True
    )
    conan_profile_string = subprocess.run(
        ["conan", "profile", "show", config[profile]["Profile"]],
        stdout=subprocess.PIPE,
        check=False
    )
    conan_profile.read_string(
        "\n".join(conan_profile_string.stdout.decode("utf-8").split("\n")[2:])
    )
    settings = conan_profile["settings"]
    compiler = settings["compiler"]
    compiler_version = settings["compiler.version"]
    config[profile].update({
        "SUFFIX": f"{compiler}{compiler_version}",
        "COMPILER": compiler,
        "OS": settings["os_build"],
    })
    if "default" in config:
        response = (
            input("Do you want to make this profile the default one (y/N): ")
            .strip()
            .lower()
        )
        if response == "y":
            config["default"]["profile"] = profile
    else:
        config["default"] = {
            "profile": profile,
        }

    with open(config_file, "w+", encoding="utf-8") as configfile:
        config.write(configfile)
    print(f"Config file {config_file} has been created.")


def check(verbose=False):
    root_repo = os.getenv("ROOTREPO")
    workspace = os.getenv("WORKSPACE")
    profile = os.getenv("PROFILE")
    build_os = os.getenv("OS")

    workspace_file = (
        Path(root_repo) / "conan" / "workspaces" / f"{workspace}.yml"
    ).resolve()

    try:
        editables = get_editables_from_ws(workspace_file)
        editable_store = EditableStore()
        cwd = os.getcwd()
        os.chdir(workspace_file.parents[0])
    except FileNotFoundError as e:
        print(f"{e} (probably wrong location to launch sph)")
        return

    print("\033[4mConanfiles and workspace integrity:\033[0m")
    for ref, details in editables.items():
        name, _, _, _, _ = split_reference_info(ref)
        editable_path = Path(details["path"]).parents[0].resolve()
        editable_store.add_editable_version(
            name, editable_path, ref, workspace_file
        )
        editable_store.store[name].path = editable_path

        conanfile = editable_path / "conan" / "conanfile.py"
        try:
            references = extract_references_from_conanfile(conanfile)
        except FileNotFoundError as e:
            print(f"\033[91m{e}\033[0m")
            continue

        for conan_ref in references:
            name, _, _, _, _ = split_reference_info(conan_ref)
            editable_store.add_editable_version(name, "", conan_ref, conanfile)

    for name, ed in editable_store.store.items():
        if ed.has_mismatch():
            good_answer = False
            print(f"\033[1m{name.capitalize()}\033[0m")
            for ver in ed.versions.values():
                print(
                    ", ".join(
                        [str(s.resolve().relative_to(cwd)) for s in ver.sources]
                    ),
                    "->",
                    ver.reference
                )
            while not good_answer:
                question = "\nOverrides:\n"
                versions = list(ed.versions.values())

                for i, version in enumerate(versions):
                    question += f"{i}: {version.reference}\n"
                question += "C: Cancel\n"
                question += f"[0-{len(versions)}/C]: "
                response = input(question) or "C"
                if response == "C":
                    good_answer = True
                else:
                    if response.isdigit():
                        int_response = int(response)
                    if int_response in range(0, len(versions)):
                        versions_values = list(ed.versions.values())
                        ref = versions_values[int_response].reference
                        good_answer = True
                        for i, version in enumerate(versions_values):
                            if i != int_response:
                                for source in version.sources:
                                    change_version(
                                        source,
                                        ed.name,
                                        versions_values[int_response].reference,
                                        version.reference,
                                    )
                    else:
                        print(f"{response} should be 0-{len(versions)}")

    if all(not ed.has_mismatch() for ed in editable_store.store.values()):
        print("No mismatch between conanfile and workspace")
    print()
    print("\033[4mRepo and conanfiles integrity:\033[0m")

    os.chdir(cwd)

    temp_file_path = "tmp_conan_info"
    # TODO(franz): check if process runs correctly
    result = subprocess.run(
        get_conan_info_command_list(
            build_os, profile, root_repo, temp_file_path
        ),
        check=False,
        stdout=None if verbose else subprocess.DEVNULL,
        stderr=None if verbose else subprocess.PIPE,
    )

    if result.returncode == 1:
        if not verbose:
            print(result.stderr.decode("utf-8"))
        return

    with open(temp_file_path, "r", encoding="utf-8") as f:
        refs = json.loads(f.read())

        for ed in refs:
            if "scm" in ed:
                reference = ed["reference"]
                conan_revision = ed["scm"]["revision"]
                editable_name, _, _, _, _ = split_reference_info(reference)
                if editable_name != root_repo:
                    editable = editable_store.get_editable(editable_name)
                    os.chdir(editable.path)

                    git_status_result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        stdout=subprocess.PIPE,
                        check=True
                    ).stdout.decode("utf-8").strip()
                    git_repo_dirty = git_status_result != ""

                    git_show_result = subprocess.run(
                        ["git", "show", "--format=\"%H\"", "-q"],
                        stdout=subprocess.PIPE,
                        check=True
                    )
                    git_revision = (
                        git_show_result.stdout.decode("utf-8").strip()[1:-1]
                    )
                    mismatch_revision = git_revision != conan_revision

                    if mismatch_revision or git_repo_dirty:
                        print(f"\033[1m{editable_name.capitalize()}\033[0m")
                    if git_repo_dirty:
                        print("Repo is dirty")
                        print(git_status_result)
                    if mismatch_revision: 
                        print(f"Local repo doesn't match {root_repo} recipe")
                        print(
                            f"{conan_revision} != {git_revision}"
                        )
                    if mismatch_revision or git_repo_dirty:
                        print()
    os.chdir(cwd)
    Path.unlink(temp_file_path)

# Allows to bump all reusable workflows versions

regex_read = "uses: (shredeagle/reusable-workflows)/\\.github/workflows/(?P<workflow>.+\\.yml)@(?P<version>.+)"
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
        print("Cannot find workflows folder in {}.".format(os.getcwd()))
        return
    for file in os.listdir(workflows_folder):
        file = os.path.join(workflows_folder, file)
        if file.endswith(".yml"):
            callback(file, *args)

def set_workflow_version(repo, version):
    walk_workflows(repo, substitute_version, version)

def get_workflow_version(repo):
    walk_workflows(repo, print_version)

def main():
    default_config_path = get_default_config_path()

    parser = argparse.ArgumentParser(
        description="Setup and build project using conan and cmake."
    )
    subparsers = parser.add_subparsers(dest="command")

    parser_workflow = subparsers.add_parser(
        "workflow", help="Change workflow version"
    )
    parser_workflow.add_argument(
        "-r",
        "--repo",
        type=str,
        default=".",
        help="Path to the configuration file",
    )
    parser_workflow.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="Show version",
    )
    parser_workflow.add_argument(
        "version",
        nargs="?",
        type=str,
        help="Version",
    )


    # Subcommand for populating config
    parser_populate = subparsers.add_parser(
        "setup", help="Populate the configuration file"
    )
    parser_populate.add_argument(
        "-c",
        "--config",
        type=str,
        default=default_config_path,
        help="Path to the configuration file",
    )
    subparsers.add_parser("config", help="Show the config")

    # Subcommand for running install commands
    parser_install = subparsers.add_parser(
        "install", help="Run the install commands"
    )
    parser_install.add_argument(
        "-c",
        "--config",
        type=str,
        default=default_config_path,
        help="Path to the configuration file",
    )
    parser_install.add_argument(
        "-p",
        "--profile",
        type=str,
        help="Configuration profile",
    )
    parser_install.add_argument(
        "-t",
        "--type",
        type=str,
        choices=["all", "clang", "visual_studio"],
        default="all",
        help="Type of install to run",
    )

    # Subcommand for checking dependencies
    parser_check = subparsers.add_parser(
        "check", help="Check conan dependencies in workspace"
    )
    parser_check.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Verbose output",
    )
    parser_check.add_argument(
        "-c",
        "--config",
        type=str,
        default=default_config_path,
        help="Path to the configuration file",
    )
    parser_check.add_argument(
        "-p",
        "--profile",
        type=str,
        help="Configuration profile",
    )
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    if args.command == "workflow":
        if args.list:
            get_workflow_version(args.repo)
        else:
            set_workflow_version(args.repo, args.version)
    elif args.command == "setup":
        setup(args.config)
    elif args.command == "config":
        subprocess.run(["cat", get_default_config_path()], check=False)
    elif args.command == "install":
        config = load_config(args.config)
        set_env_vars(
            config[args.profile]
            if args.profile
            else config[config["default"]["profile"]]
        )
        install()
    elif args.command == "check":
        config = load_config(args.config)
        set_env_vars(
            config[args.profile]
            if args.profile
            else config[config["default"]["profile"]]
        )
        check(args.verbose)
    else:
        parser.print_help()
