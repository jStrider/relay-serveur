"""Abonnement : barrière `abonne_requis`, et vérification des transactions App Store (JWS signé par Apple)
avec la bibliothèque officielle. `RELAY_GRATUIT=1` désactive toute barrière (auto-hébergement)."""

import sqlite3
import time
from pathlib import Path
from typing import Protocol

from fastapi import APIRouter, HTTPException, Request

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


class Verificateur(Protocol):
    def expire_le(self, jws: str) -> float:
        """Horodatage (secondes) de fin de l'abonnement porté par la transaction ; ValueError si elle est invalide."""


class VerificateurApple:
    """Vérifie la chaîne de signature (racines Apple en local, pas d'appel réseau), le bundle et l'app."""

    def __init__(self, config):
        from appstoreserverlibrary.models.Environment import Environment
        from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier

        racines = [p.read_bytes() for p in sorted(Path(config.apple_racines).glob("*.cer"))]
        if not racines:
            raise ValueError(f"aucun certificat racine Apple dans {config.apple_racines!r}")
        env = Environment.PRODUCTION if config.apple_env.lower() == "production" else Environment.SANDBOX
        self._verificateur = SignedDataVerifier(racines, False, env, config.apns_bundle, config.apple_app_id or None)

    def expire_le(self, jws: str) -> float:
        from appstoreserverlibrary.signed_data_verifier import VerificationException

        try:
            transaction = self._verificateur.verify_and_decode_signed_transaction(jws)
        except (VerificationException, ValueError, TypeError) as e:
            raise ValueError(f"transaction refusée : {type(e).__name__}") from None
        if not transaction.expiresDate:
            raise ValueError("transaction sans date d'expiration")
        return transaction.expiresDate / 1000


class VerificateurAbsent:
    """Serveur sans configuration Apple (auto-hébergement gratuit, tests) : aucune transaction n'est acceptée."""

    def expire_le(self, jws: str) -> float:
        raise ValueError("vérification App Store non configurée")


def depuis_config(config) -> Verificateur:
    return VerificateurApple(config) if config.apple_racines else VerificateurAbsent()


def routeur(verificateur: Verificateur) -> APIRouter:
    r = APIRouter()

    @r.post("/abonnement")
    def enregistrer_abonnement(corps: dict, request: Request):
        compte = compte_courant(request)
        jws = corps.get("transaction")
        if not isinstance(jws, str) or not jws:
            raise HTTPException(400, "transaction attendue")
        try:
            expire = verificateur.expire_le(jws)
        except ValueError:
            raise HTTPException(400, "transaction invalide")
        request.app.state.base.execute("update comptes set abonne_jusqu_au = ? where id = ?", (expire, compte))
        return {"abonne_jusqu_au": expire}

    return r
