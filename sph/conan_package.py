class ConanPackage:
    """ Represents a unique conan package """
    name: str

    def __init__(self, name, editable=None):
        self.name = name
        self.editable = editable

    def __eq__(self, other):
        return hasattr(other, 'name') and self.name == other.name

    def __str__(self):
        return self.name

    def __hash__(self):
        return self.name.__hash__()
