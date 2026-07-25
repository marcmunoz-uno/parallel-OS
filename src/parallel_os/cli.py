"""parallel-os CLI — drive the runtime host from the shell or over SSH.

    parallel-os runtimes                      # list available runtime specs
    parallel-os spawn netshoot                # -> {"container_id": "...", ...}
    parallel-os exec <cid> dig +short github.com
    parallel-os list                          # live runtimes
    parallel-os reap <cid>

Emits JSON on stdout (one object) so callers can parse it. Also runnable as
`python -m parallel_os`.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import runtimes
from .host import Host


def main(argv: list[str] | None = None) -> int:
    # keep stdout pure JSON for programmatic callers; send logs to stderr
    try:
        import structlog
        structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="parallel-os")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("runtimes", help="list registered runtime specs")
    sub.add_parser("list", help="list live runtimes")
    sp = sub.add_parser("spawn", help="spawn a runtime")
    sp.add_argument("runtime")
    sp.add_argument("--ttl", type=int, default=None)
    sp.add_argument("--agent", default=None)
    ex = sub.add_parser("exec", help="exec a command in a runtime")
    ex.add_argument("--timeout", type=int, default=60)
    ex.add_argument("container_id")
    ex.add_argument("command", nargs=argparse.REMAINDER)
    rp = sub.add_parser("reap", help="stop + remove a runtime")
    rp.add_argument("container_id")

    a = ap.parse_args(argv)
    out: object
    if a.cmd == "runtimes":
        out = {k: {"image": v.image, "network": v.network_mode}
               for k, v in runtimes.REGISTRY.items()}
    else:
        host = Host()
        if a.cmd == "spawn":
            out = host.spawn(a.runtime, agent_id=a.agent, ttl_sec=a.ttl)
        elif a.cmd == "exec":
            if not a.command:
                ap.error("exec needs a command")
            out = host.exec(a.container_id, a.command, timeout_sec=a.timeout)
        elif a.cmd == "reap":
            out = host.reap(a.container_id)
        elif a.cmd == "list":
            out = host.list()
        else:  # pragma: no cover
            ap.error(f"unknown command {a.cmd}")
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
