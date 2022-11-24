def compute_conflicts(workspaces, editable_list):
    editable_version_by_name = dict()

    for workspace in workspaces:
        for ref, _ in workspace.local_refs:
            if ref.package.name not in editable_version_by_name:
                editable_version_by_name[ref.package.name] = dict()

            if ref.ref not in editable_version_by_name[ref.package.name]:
                editable_version_by_name[ref.package.name][ref.ref] = set()

            editable_version_by_name[ref.package.name][ref.ref].add(workspace)



        for e in editable_list:
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

        for e in editable_list:
            for req in e.required_local_lib:
                for ref_needed, value in editable_version_by_name[req.package.name].items():
                    if (e.package not in value) and (ref_needed is not req.ref):
                        req.conflicts.update(value)

            for req in e.required_external_lib:
                for ref_needed, value in editable_version_by_name[req.package.name].items():
                    if (e.package not in value) and (ref_needed is not req.ref):
                        req.conflicts.update(value)

