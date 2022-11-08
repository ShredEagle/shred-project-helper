from typing_extensions import Any
from sph.conan_package import ConanPackage
from sph.utils import extract_info_from_conan_ref, t

class ConanRef:
    @property
    def ref(self):
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
        self.is_present_locally = False

    def __eq__(self, other):
        return hasattr(other, 'ref') and self.ref == other.ref

    def __str__(self):
        return f'{self.ref}'
    
    def __hash__(self):
        return self.ref.__hash__()
