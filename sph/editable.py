import re
from collections import namedtuple
from .utils import split_reference_info


class Version:
    def __init__(self, reference, source):
        self.reference = reference
        _, version, _, _, _ = split_reference_info(reference)
        self.version = version
        self.sources = {source}

    def __hash__(self):
        return hash(self.version)

    def __eq__(self, other):
        return hash(self) == hash(other)


class Editable:
    def __init__(self, name):
        self.name = name
        self.versions = {}
        self.path = None

    def has_mismatch(self):
        return len(self.versions.items()) > 1
    
    def add_version(self, version):
        if version.version in self.versions:
            old_version = self.versions[version.version]
            old_version.sources.update(version.sources)
        else:
            self.versions[version.version] = version



class EditableStore:
    def __init__(self):
        self.store = {}

    def get_editable(self, name):
        return self.store.get(name)

    def add_editable_version(self, name, path, reference, source):
        if name not in self.store:
            self.store[name] = Editable(name)

        self.store[name].add_version(Version(reference, source))
