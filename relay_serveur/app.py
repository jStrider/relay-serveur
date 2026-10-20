"""Application FastAPI : les routes sont posées par les modules métier sur une app commune."""

import sqlite3

from fastapi import FastAPI

from . import abonnement, apns, appairages, blobs, comptes, limites, rafraichir
from .config import Config


def creer_app(config: Config, base: sqlite3.Connection, envoyeur=None, verificateur=None) -> FastAPI:
    app = FastAPI(title="Relay", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.state.base = base
    app.state.envoyeur = envoyeur
    app.state.verificateur = verificateur

    limites.installer(app)

    @app.get("/sante")
    def sante():
        return {"status": "ok"}

    app.include_router(comptes.routeur())
    app.include_router(blobs.routeur())
    envoyeur = envoyeur or apns.Envoyeur(config)
    app.include_router(rafraichir.routeur(rafraichir.Rafraichisseur(base, envoyeur, config)))
    app.include_router(abonnement.routeur(verificateur or abonnement.depuis_config(config)))
    app.include_router(appairages.routeur())

    return app
