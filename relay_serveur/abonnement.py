"""Abonnement : barrière `abonne_requis`, et vérification des transactions App Store (JWS signé par Apple)
avec la bibliothèque officielle. Une transaction vaut pour un seul compte : son identifiant d'origine est
gardé avec un index unique, et si l'app a posé un appAccountToken il doit être celui du compte.
`RELAY_GRATUIT=1` désactive toute barrière (auto-hébergement)."""

import sqlite3
import time
import uuid
from dataclasses import dataclass
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


def jeton_de_compte(compte: str) -> str:
    """UUID que l'app pose comme appAccountToken à l'achat : dérivé de l'identifiant, sans secret."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "relay:" + compte))


@dataclass
class Transaction:
    expire_le: float  # secondes
    origine: str  # originalTransactionId : identifie l'abonnement à travers ses renouvellements
    revoquee: bool = False
    app_account_token: str | None = None


class Verificateur(Protocol):
    def verifier(self, jws: str) -> Transaction:
        """Transaction décodée si la signature, le bundle et l'app sont bons ; ValueError sinon."""


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

    def verifier(self, jws: str) -> Transaction:
        from appstoreserverlibrary.signed_data_verifier import VerificationException

        try:
            t = self._verificateur.verify_and_decode_signed_transaction(jws)
        except (VerificationException, ValueError, TypeError) as e:
            raise ValueError(f"transaction refusée : {type(e).__name__}") from None
        if not t.expiresDate or not t.originalTransactionId:
            raise ValueError("transaction sans expiration ou sans identifiant d'origine")
        return Transaction(expire_le=t.expiresDate / 1000, origine=str(t.originalTransactionId),
                           revoquee=bool(t.revocationDate), app_account_token=str(t.appAccountToken) if t.appAccountToken else None)


class VerificateurAbsent:
    """Serveur sans configuration Apple (auto-hébergement gratuit, tests) : aucune transaction n'est acceptée."""

    def verifier(self, jws: str) -> Transaction:
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
            t = verificateur.verifier(jws)
        except ValueError:
            raise HTTPException(400, "transaction invalide")
        if t.revoquee:
            raise HTTPException(400, "transaction révoquée")
        if t.app_account_token and t.app_account_token.lower() != jeton_de_compte(compte):
            raise HTTPException(400, "transaction d'un autre compte")
        base = request.app.state.base
        autre = base.execute("select id from comptes where transaction_origine = ? and id != ?", (t.origine, compte)).fetchone()
        if autre:
            raise HTTPException(409, "transaction déjà utilisée par un autre compte")
        base.execute("update comptes set abonne_jusqu_au = ?, transaction_origine = ? where id = ?", (t.expire_le, t.origine, compte))
        return {"abonne_jusqu_au": t.expire_le}

    return r
