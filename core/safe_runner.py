"""Runs a function in a separate process and hard-kills it if it takes
too long -- protects the server from overload caused by (intentionally
or accidentally) very expensive input, e.g. huge symbolic integrals,
tall power towers, or large matrices.

Deliberately a separate PROCESS rather than a thread: a hanging/CPU-
heavy SymPy call can't be cleanly killed out of a thread in Python --
the thread would keep running in the background and consuming CPU even
after the HTTP request has long since been answered with an error. A
child process, on the other hand, can actually be terminated via
terminate()/kill() and gives its resources back -- this protects the
server itself, not just the individual response.
"""

from __future__ import annotations

import multiprocessing as mp

DEFAULT_TIMEOUT_SECONDS = 10


def _worker(queue: mp.Queue, func, args: tuple, kwargs: dict) -> None:
    try:
        result = func(*args, **kwargs)
        queue.put(("ok", result))
    except Exception as exc:  # noqa: BLE001 -- error text is passed through
        queue.put(("error", str(exc)))


def run_with_timeout(func, args: tuple = (), kwargs: dict | None = None,
                      timeout: float = DEFAULT_TIMEOUT_SECONDS):
    """Runs func(*args, **kwargs) in a child process.

    Returns a tuple (status, value):
        ("ok", result)     -- ran normally
        ("error", message) -- an exception was raised in the child process
        ("timeout", None)  -- ran longer than `timeout` seconds, process
                               was killed

    func AND its arguments/return value must be picklable (true for
    core.engine.evaluate_code(): only strings/numbers/lists/dicts, no
    SymPy objects in the return value).
    """
    kwargs = kwargs or {}
    queue: mp.Queue = mp.Queue()
    process = mp.Process(target=_worker, args=(queue, func, args, kwargs))
    process.start()
    process.join(timeout)

    if process.is_alive():
        process.terminate()
        process.join(2)
        if process.is_alive():
            process.kill()
            process.join()
        return "timeout", None

    if not queue.empty():
        return queue.get()

    # Process ended without writing anything to the queue (e.g. an
    # OOM-kill or a crash inside a C extension) -- treat this as a clear
    # error instead of surfacing a cryptic exception.
    return "error", "Computation ended unexpectedly (e.g. memory limit)."
