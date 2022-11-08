from concurrent.futures import ThreadPoolExecutor
import re
import time
import pdb

class Choice:
    def __init__(self, conan_ref, editable, conflicted_editable, thread_pool, from_github=False):
        self.thread_pool = thread_pool
        self.ref = conan_ref
        self.editable = editable
        self.waiting = True
        self.conflicted_editable = conflicted_editable
        self.from_github = from_github

    def resolve_conflict(self, new_dependency):
        self.conflicted_editable.change_version(new_dependency, self.ref.ref)

    def __str__(self):
        result = '  ' + self.ref.ref

        if self.waiting and self.editable and self.editable.gh_repo and self.ref.date is None:
            self.waiting = False
            self.thread_pool.submit(self.fill_date_from_github)

        if self.ref.date is not None:
            if not self.ref.date:
                result += " - Waiting for date"
            else:
                result += f'{self.ref.date.strftime(" - %Y/%m/%d %H:%M:%S")}'

        return result

    def fill_date_from_github(self):
            match = re.search(r"/([\w]{10})", self.ref.ref)

            if match:
                self.ref.date = False
                if self.editable.gh_repo is not None and self.editable.gh_repo is not False:
                    commit = self.editable.gh_repo.get_commit(match.group(1)).commit
                    self.ref.date = commit.author.date

