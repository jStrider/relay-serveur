"""Application FastAPI : les routes sont posées par les modules métier sur une app commune."""

import sqlite3

from fastapi import FastAPI

from . import comptes
from .config import Config


def creer_app(config: Config, base: sqlite3.Connection, envoyeur=None, verificateur=None) -> FastAPI:
    app = FastAPI(title="Relay", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.state.base = base
    app.state.envoyeur = envoyeur
    app.state.verificateur = verificateur

    @app.get("/sante")
    def sante():
        return {"status": "ok"}

    app.include_router(comptes.routeur())

    return app
