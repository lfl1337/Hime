"""
Port-selection utility.

Scans upward from ``start`` until a port is available on 127.0.0.1.
Uses a real bind-attempt so the result is accurate even when a process
holds a port without advertising it in netstat/ss.
"""
import socket


def find_free_port(start: int = 8000, *, max_tries: int = 100) -> int:
    """Return the first free TCP port in the range [start, start + max_tries)."""
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        f"No free port found in range {start}–{start + max_tries - 1}"
    )
