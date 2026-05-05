"""Example: a single agent uses three runtimes in parallel.

Status: requires the orchestrator + MCP wiring to be implemented first.
This file documents the intended developer experience.
"""

from __future__ import annotations

import asyncio

from parallel_os import Runtime, Swarm


async def main() -> None:
    target = "example.com"

    # Single runtime usage
    async with Runtime.spawn("kali", ttl_sec=900) as kali:
        subdomains_result = await kali.tool.amass.enum(domain=target)
        print(f"amass found {len(subdomains_result.subdomains)} subdomains")

        for subdomain in subdomains_result.subdomains[:5]:
            fp = await kali.tool.whatweb.fingerprint(url=f"https://{subdomain}")
            print(f"  {subdomain}: {fp.tech_stack}")

    # Multi-runtime parallel usage
    async with Swarm.spawn(["kali", "ubuntu", "arch"]) as swarm:
        results = await asyncio.gather(
            swarm.kali.tool.linkfinder.scan(
                js_url_or_path=f"https://{target}/static/main.js"
            ),
            swarm.ubuntu.shell.run("apt-cache search nginx-extras"),
            swarm.arch.pkg.install("aur-helper"),
        )
        print("kali endpoints discovered:", results[0])
        print("ubuntu apt search:", results[1])
        print("arch package install:", results[2])


if __name__ == "__main__":
    asyncio.run(main())
