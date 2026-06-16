"""
atunnel: A minimal Python package to expose localhost to the public internet
using Cloudflare's cloudflared tunnel (quick tunnels).
"""

from atunnel.tunnel import Tunnel

__all__ = ["Tunnel"]
__version__ = "1.0.1"
