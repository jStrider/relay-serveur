"""Barrière d'abonnement : `est_abonne` et la dépendance `abonne_requis`. La vérification des transactions
App Store vient dans un second temps (tâche 6)."""

import sqlite3
import time

from fastapi import HTTPException, Request

from .comptes import compte_courant


def est_abonne(base: sqlite3.Connection, compte: str, maintenant: float, gratuit: bool = False) -> bool:
    if gratuit:
        return True
    ligne = base.execute("select abonne_jusqu_au from comptes where id = ?", (compte,)).fetchone()
    return bool(ligne and ligne[0] and ligne[0] > maintenant)


def abonne_requis(request: Request) -> str:
    """Dépendance FastAPI : le compte authentifié, abonné (ou serveur gratuit), sinon 402."""
    compte = compte_courant(request)
    if not est_abonne(request.app.state.base, compte, time.time(), request.app.state.config.gratuit):
        raise HTTPException(402, "abonnement requis")
    return compte
