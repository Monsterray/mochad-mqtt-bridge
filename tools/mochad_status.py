#!/usr/bin/env python3
"""
Request `st` from mochad and print received lines from inside the bridge image.
"""

from __future__ import annotations

import argparse
import socket
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="mochad")
    parser.add_argument("--port", type=int, default=1099)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    try:
        with socket.create_connection(
            (args.host, args.port),
            timeout=args.timeout,
        ) as sock:
            sock.settimeout(args.timeout)
            sock.sendall(b"st\n")

            while True:
                data = sock.recv(4096)

                if not data:
                    return 0

                text = data.decode("utf-8", errors="replace")
                print(text, end="")

                if "End status" in text:
                    return 0
    except OSError as exc:
        print(
            f"FAIL status request failed for {args.host}:{args.port}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
