"""
Vercel Python entrypoint.

Vercel's Python runtime serves the exported ASGI `app` directly. With
root directory = /backend and the rewrite in vercel.json, every request is
routed here.
"""
from app.main import app  # noqa: F401

# Vercel looks for a module-level ASGI callable named `app`.
