from __future__ import annotations

import os
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from loop_agent import __version__
from loop_agent.api import routes

_DEFAULT_LOCAL_ORIGINS = [
    "http://localhost",
    "http://localhost:*",
    "http://127.0.0.1",
    "http://127.0.0.1:*",
    "https://localhost",
    "https://localhost:*",
    "https://127.0.0.1",
    "https://127.0.0.1:*",
]


def _allowed_origins() -> list[str]:
    """Resolve CORS allow-origins from environment.

    ``LOOP_AGENT_CORS_ORIGINS`` is a comma-separated list. Empty entries
    are ignored. When the variable is unset we default to a tight
    localhost-only list so dev-mode browser UIs work out of the box
    without exposing the API to arbitrary remote origins.
    """
    env = os.environ.get("LOOP_AGENT_CORS_ORIGINS", "")
    if not env.strip():
        return list(_DEFAULT_LOCAL_ORIGINS)
    extras = [o.strip() for o in env.split(",") if o.strip()]
    seen = set(_DEFAULT_LOCAL_ORIGINS)
    origins = list(_DEFAULT_LOCAL_ORIGINS)
    for origin in extras:
        if origin not in seen:
            origins.append(origin)
            seen.add(origin)
    return origins


def _origin_regex() -> str | None:
    """Return a regex that matches localhost with any port.

    ``CORSMiddleware`` does not expand ``*`` wildcards in origins, but it
    does support ``allow_origin_regex``. We use that so the default
    localhost origins cover any dev-server port without listing each one.
    """
    return r"https?://(localhost|127\.0\.0\.1)(:\d+)?"


def create_app() -> FastAPI:
    app = FastAPI(title="loop-agent", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_origin_regex=_origin_regex(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Run-ID", "X-Request-ID"],
    )
    app.include_router(routes.router)
    return app


app = create_app()
