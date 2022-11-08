class ConanPackage:
    name: str

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return hasattr(other, 'name') and self.name == other.name
    
    def __str__(self):
        return self.name

    def __hash__(self):
        return self.name.__hash__()
