# A-tunnel
A minimal Python package to expose localhost to the public internet using [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/).

No Cloudflare account required  generates a temporary `*.trycloudflare.com` URL.

## 😂 Why A-tunnel Exists

We've all seen that:


https://github.com/user-attachments/assets/6760cfc2-c917-40bf-aff6-9563e0dcfe9d



**Before**: "Bro, check out my website! http://localhost:3000" 😅

**After**: "Bro, check out my website! https://your-site.trycloudflare.com" ✨

## Installation

```bash
# Using pip
pip install atunnel

# Or using uv
uv add atunnel
```

## Usage

### CLI

```bash
# Expose local port 8080
atunnel --port 8080

# With uv
uv run atunnel --port 8080
```

The public URL is printed to stdout. Press Ctrl+C to stop.

### Python API

```python
from atunnel.tunnel import Tunnel

with Tunnel(port=8080) as t:
    print(f"Public URL: {t.public_url}")
    input("Press Enter to stop...")
```
##  Security Notice

**A-tunnel exposes your local development server to the public internet!** 

Please keep the following in mind:
- **Don't expose sensitive data**: Never use A-tunnel with development servers that have access to production databases, API keys, or sensitive information
- **Use authentication**: Ensure your development application has proper authentication enabled
- **Not for production**: This tool is designed for development and testing purposes only

