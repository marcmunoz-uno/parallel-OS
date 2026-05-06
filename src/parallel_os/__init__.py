"""parallel-OS — multi-OS execution framework for AI agents."""

__version__ = "0.0.4"

from parallel_os.sdk.client import Runtime, Swarm
from parallel_os.services import Manifest, Service, load

__all__ = ["Runtime", "Swarm", "Manifest", "Service", "load", "__version__"]
