from typing_extensions import Any
from sph.conan_package import ConanPackage
from sph.utils import extract_info_from_conan_ref, t

class ConanRef:
    @property
    def conan_ref(self):
        ref = f'{self.package.name}/{self.version}'

        if self.user:
            ref += f'@{self.user}/{self.channel}'

        if self.revision != "":
            ref += f'#{self.revision}'

        return ref

    def __init__(self, ref):
        name, version, user, channel, revision = extract_info_from_conan_ref(
                ref
            )
        self.package = ConanPackage(name)
        self.version = version
        self.user = user
        self.channel = channel
        self.revision = revision
        self.conflicts = set() 
        self.editable =None
        self.date = None

    def __eq__(self, other):
        return self.conan_ref == other.conan_ref

    def __str__(self):
        return f'{self.conan_ref}'
    
    def __hash__(self):
        return self.conan_ref.__hash__()
