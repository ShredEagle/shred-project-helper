import re

class Semver:
    def __init__(self, version):
        semver_regex = r"(\d+)\.(\d+)\.(\d+)"
        match = re.search(semver_regex, version)

        if match:
            self.major = match.group(1)
            self.minor = match.group(2)
            self.patch = match.group(3)

    def __str__(self):
        return f"{self.major}.{self.minor}.{self.patch}"

    def __eq__(self, other):
        if not isinstance(other, Semver):
            return False

        return (self.major == other.major and 
            self.minor == other.minor and self.patch == other.patch)

    def __gt__(self, other):
        return self.major > other.major or (
                self.major == other.major and self.minor > other.minor
                ) or (
                self.major == other.major and self.minor == other.minor and self.patch > other.patch
                )

    def __lt__(self, other):
        return self.major < other.major or (
                self.major == other.major and self.minor < other.minor
                ) or (
                self.major == other.major and self.minor == other.minor and self.patch < other.patch
                )

