class Conflict:
    def __init__(self, ConanRefDescriptor):
        self.ref = ConanRefDescriptor

    def __str__(self):
        return '  ' + self.ref.conan_ref
