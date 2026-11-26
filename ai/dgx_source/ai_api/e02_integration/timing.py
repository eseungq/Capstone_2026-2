"""Request-local measurements for the e02 JSONL audit."""
from contextvars import ContextVar
from time import perf_counter


REQUEST_TIMINGS = ContextVar("e02_request_timings", default=None)
STAGES = ("imageDownloadMs", "preprocessingMs", "camGenerationMs", "modelLockWaitMs")


def measure(field, operation, *args):
    timings = REQUEST_TIMINGS.get()
    if timings is None or timings[field] is not None:
        return operation(*args)
    started = perf_counter()
    try:
        return operation(*args)
    finally:
        timings[field] = (perf_counter() - started) * 1000


class TimedModelLock:
    def __init__(self, lock):
        self.lock = lock

    def __enter__(self):
        return measure("modelLockWaitMs", self.lock.__enter__)

    def __exit__(self, exc_type, exc_value, traceback):
        return self.lock.__exit__(exc_type, exc_value, traceback)
