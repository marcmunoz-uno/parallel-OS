# Kali runtime for parallel-OS
# Allowlisted OSINT/recon toolset. Nothing offensive — no metasploit, sqlmap,
# hashcat, john, aircrack-ng, exploitdb. See tools.json for the full registry.

FROM kalilinux/kali-rolling

LABEL parallel-os.runtime="kali"
LABEL parallel-os.image-version="kali-rolling-2026-q2"

ENV DEBIAN_FRONTEND=noninteractive

# Install only the allowlisted tools. Each is a deliberate inclusion.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        # Network reconnaissance
        amass dnsutils dnsenum \
        # Web scanning (passive)
        whatweb gobuster wfuzz \
        # Traffic interception
        mitmproxy \
        # JS / endpoint analysis
        python3-pip python3-venv \
        # Cloud / leak hunting
        trufflehog \
        # Generic tooling
        curl jq git ca-certificates \
        # MCP server runtime
        python3-aiohttp python3-pydantic && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Pip-only tools
RUN pip install --no-cache-dir --break-system-packages \
        linkfinder \
        secretfinder \
        arjun \
        nuclei  # nuclei has a Go binary too; the pip wrapper is convenient

# Explicitly REMOVE anything offensive that might be in the base image
RUN apt-get remove -y --purge \
        metasploit-framework \
        sqlmap \
        hashcat hashcat-utils \
        john john-data \
        aircrack-ng \
        exploitdb \
        2>/dev/null || true

# parallel-OS MCP server lives in /opt/parallel-os
COPY mcp_server.py /opt/parallel-os/mcp_server.py
COPY tools.json /etc/parallel-os/tools.json

RUN useradd -r -u 65534 -g 65534 -s /usr/sbin/nologin agent || true
RUN mkdir -p /work && chown 65534:65534 /work

USER 65534:65534
WORKDIR /work

# MCP server speaks JSON-RPC over stdio
ENTRYPOINT ["python3", "/opt/parallel-os/mcp_server.py"]
