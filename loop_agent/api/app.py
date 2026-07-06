from __future__ import annotations

from fastapi import FastAPI

from loop_agent import __version__
from loop_agent.api import routes


def create_app() -> FastAPI:
    app = FastAPI(title="loop-agent", version=__version__)
    app.include_router(routes.router)
    return app


app = create_app()
