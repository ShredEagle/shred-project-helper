from sph.utils import extract_info_from_conan_ref, t

class ConanRefDescriptor:
    conan_ref: str
    name: str
    version: str
    user: str
    channel: str
    revision: str
    conflicts: set

    def __init__(self, ref):
        name, version, user, channel, revision = extract_info_from_conan_ref(
                ref
            )
        self.conan_ref = ref
        self.name = name
        self.version = version
        self.user = user
        self.channel = channel
        self.revision = revision
        self.conflicts = set() 

    def __eq__(self, other):
        return self.conan_ref == other.conan_ref

    def __str__(self, level=0):
        return f'''{t(level)}{self.conan_ref}:
{t(level + 1)}name: {self.name}
{t(level + 1)}version: {self.version}
{t(level + 1)}user: {self.user}
{t(level + 1)}channel: {self.channel}
{t(level + 1)}revision: {self.revision}
{t(level + 1)}conflicts: {self.conflicts}
'''
    
    def __hash__(self):
        return self.conan_ref.__hash__()

    def print_check(self, level=0):
        if len(self.conflicts) > 0:
            ret = f"{t(level)}{self.conan_ref} conflicts with "
            for c in self.conflicts:
                for name in c:
                    ret += f"{Fore.RED}{name}{Fore.RESET} "
            Halo(ret).fail()
        else:
            ret = f"{t(level)}{self.conan_ref} is ok"
            Halo(ret).succeed()

