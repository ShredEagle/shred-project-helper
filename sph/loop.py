import asyncio
# TODO: use signal and a main worker loop
class Loop:
    def __init__(self):
        self.loop = asyncio.get_event_loop()
    
    def run_safe_in_executor(self, *args):
        future = self.loop.run_in_executor(*args)
        future.add_done_callback(self.exception_callback)

    def exception_callback(self, future):
        future.result()
