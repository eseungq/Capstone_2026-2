"""Request-local measurements for the e02 JSONL audit."""
from contextvars import ContextVar
from time import perf_counter


REQUEST_TIMINGS = ContextVar("e02_request_timings", default=None)
STAGES = ("imageDownloadMs", "preprocessingMs", "camGenerationMs")


def measure(field, operation, *args):
    timings = REQUEST_TIMINGS.get()
    if timings is None or timings[field] is not None:
        return operation(*args)
    started = perf_counter()
    try:
        return operation(*args)
    finally:
        timings[field] = (perf_counter() - started) * 1000
