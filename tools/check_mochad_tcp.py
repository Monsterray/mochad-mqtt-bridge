#!/usr/bin/env python3
"""
Check whether a mochad TCP endpoint is reachable from inside the bridge image.
"""

from __future__ import annotations

import argparse
import socket
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="mochad")
    parser.add_argument("--port", type=int, default=1099)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    try:
        with socket.create_connection(
            (args.host, args.port),
            timeout=args.timeout,
        ):
            print(f"PASS connected to {args.host}:{args.port}")
            return 0
    except OSError as exc:
        print(
            f"FAIL could not connect to {args.host}:{args.port}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
