class SphException(Exception):
    pass

class PackageNotFound(SphException):
    pass

class EditableNotInFilesystem(SphException):
    pass

class RegexpFormatException(SphException):
    pass
