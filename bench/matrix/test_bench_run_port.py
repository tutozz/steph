"""bench_run.py refuses a port another llama-server already holds (X5: a run silently hit
someone else's server when its own could not bind).

    python3 -m pytest bench/matrix/test_bench_run_port.py -q

SPDX-License-Identifier: MIT
"""

import socket

import bench_run


def test_busy_port_is_detected():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        assert bench_run.port_in_use(s.getsockname()[1]) is True


def test_free_port_is_not_busy():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert bench_run.port_in_use(port) is False
