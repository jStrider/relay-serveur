"""Débit par compte, journal sans aucune donnée, erreur interne sans détail, compteurs d'usage du jour."""

import logging
import sqlite3
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .comptes import authentifier

journal = logging.getLogger("relay")


def installer(app: FastAPI) -> None:
    config = app.state.config
    fenetres: dict[str, deque] = defaultdict(deque)

    # Les exceptions des routes sont traitées par Starlette hors des middlewares : le gestionnaire global
    # garantit une réponse sans détail, le journal garde la trace.
    async def erreur_interne(request: Request, exc: Exception):
        journal.error("%s %s 500 : %s", request.method, request.url.path, type(exc).__name__)
        return JSONResponse({"status": "erreur interne"}, status_code=500)

    app.add_exception_handler(Exception, erreur_interne)

    @app.middleware("http")
    async def debit_et_journal(request: Request, suite):
        debut = time.time()
        compte = authentifier(app.state.base, request.headers.get("Authorization")) if request.headers.get("Authorization") else None
        if compte:
            f = fenetres[compte]
            while f and f[0] < debut - 60:
                f.popleft()
            if len(f) >= config.requetes_par_minute:
                journal.info("%s %s 429 %s %dms", request.method, request.url.path, compte, 0)
                return JSONResponse({"status": "trop de requêtes"}, status_code=429)
            f.append(debut)
        try:
            reponse = await suite(request)
        except Exception:
            journal.exception("%s %s 500 %s", request.method, request.url.path, compte or "-")
            reponse = JSONResponse({"status": "erreur interne"}, status_code=500)
        journal.info("%s %s %d %s %dms", request.method, request.url.path, reponse.status_code, compte or "-", (time.time() - debut) * 1000)
        return reponse


def ecrire_compteurs(base: sqlite3.Connection, chemin: str, maintenant: float) -> None:
    """Une ligne par jour : date, comptes vus dans la journée, etat.json déposés dans la journée. Rien de nominatif."""
    if not chemin:
        return
    jour = datetime.fromtimestamp(maintenant, timezone.utc).date()
    debut_jour = datetime(jour.year, jour.month, jour.day, tzinfo=timezone.utc).timestamp()
    actifs = base.execute("select count(*) from comptes where vu_le >= ?", (debut_jour,)).fetchone()[0]
    synchros = base.execute("select count(*) from blobs where nom = 'etat.json' and maj >= ?", (debut_jour,)).fetchone()[0]
    lignes = []
    try:
        lignes = [l for l in open(chemin, encoding="utf-8").read().splitlines() if not l.startswith(jour.isoformat())]
    except OSError:
        pass
    lignes.append(f"{jour.isoformat()} {actifs} {synchros}")
    with open(chemin, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes) + "\n")
