from concurrent.futures import ThreadPoolExecutor
import re
import time
import pdb


class Conflict:
    def __init__(self, conan_ref, editable):
        self.ref = conan_ref
        self.editable = editable
        self.waiting = True

    def __str__(self):
        result = '  ' + self.ref.conan_ref

        if self.waiting and self.ref.date is None:
            self.waiting = False
            exe = ThreadPoolExecutor(max_workers=1)
            exe.submit(self.fill_date_from_github)

        if self.ref.date:
            result += f'{self.ref.date}'

        return result

    # FIX: this needs to wait for the gh_repo before being executed
    def fill_date_from_github(self):
        match = re.search(r"/([\w]{10})", self.ref.conan_ref)

        if match:
            self.ref.date = " - Waiting for date"
            if self.editable.gh_repo:
                commit = self.editable.gh_repo.get_commit(match.group(1)).commit
                self.ref.date = commit.author.date.strftime(" - %Y/%m/%d %H:%M:%S")
