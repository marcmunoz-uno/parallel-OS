"""Kali runtime MCP server (skeleton).

Runs inside the Kali container. Exposes the allowlisted tools from tools.json
as MCP tools. Speaks JSON-RPC over stdio.

Status: skeleton. Real implementation routes JSON-RPC requests through a
shell-exec layer that validates against tools.json before invoking the binary.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def load_manifest() -> dict:
    path = Path(os.environ.get("PARALLEL_OS_TOOLS_MANIFEST", "/etc/parallel-os/tools.json"))
    return json.loads(path.read_text())


def main() -> None:
    manifest = load_manifest()
    print(
        json.dumps({
            "type": "ready",
            "runtime": manifest["runtime"],
            "image_version": manifest["image_version"],
            "tools": list(manifest.get("tools", {}).keys()),
        }),
        flush=True,
    )
    # TODO: implement JSON-RPC over stdio loop:
    #   - parse request
    #   - validate tool name against manifest
    #   - render args from template + caller args
    #   - exec subprocess with timeout
    #   - return structured result
    # Use the official `mcp` Python package once it's stable on Kali ARM.
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Echo for now — real handler comes next.
        print(
            json.dumps({"type": "ack", "echoed": req, "note": "handler not implemented yet"}),
            flush=True,
        )


if __name__ == "__main__":
    main()
