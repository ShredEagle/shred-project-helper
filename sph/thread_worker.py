from concurrent.futures import ThreadPoolExecutor

class Worker:
    def __init__(self):
        self.jobs = dict()
        self.thread_pool = ThreadPoolExecutor(max_workers=8)
    
    def remove_job_callback(self, id):
        def remove_job(future):
            self.jobs[id] = None
        return remove_job

    def push_work(self, id, func):
        if id not in self.jobs or not self.jobs[id]:
            self.jobs[id] = self.thread_pool.submit(func)
            self.jobs[id].add_done_callback(self.remove_job_callback(id))
    
    def cancel(self):
        for id, value in self.jobs.items():
            if value:
                value.cancel()
        self.thread_pool.shutdown()
    
    def done(self):
        for id, value in self.jobs.items():
            if value and not value.done():
                value.cancel()
                return False
        return True
    
    def exception(self):
        for id, value in self.jobs.items():
            if value and value.exception():
                raise(value.exception())
