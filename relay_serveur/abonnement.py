"""Abonnement : barrière `abonne_requis`, et vérification des transactions App Store (JWS signé par Apple)
avec la bibliothèque officielle. Une transaction vaut pour un seul compte à la fois : son identifiant d'origine
est gardé avec un index unique. La première fois qu'elle est présentée, si l'app a posé un appAccountToken, il doit
être celui du compte ; ensuite, elle passe au compte qui la présente (phrase régénérée, compte supprimé, nouvel
iPhone : l'identifiant du compte change, l'abonnement le suit, l'ancien compte le perd).
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
    """Vérifie la chaîne de signature (racines Apple en local, pas d'appel réseau), le bundle et l'app.
    Comme le recommande Apple, en production d'abord, puis en sandbox si l'environnement ne correspond pas
    (achats TestFlight et du relecteur Apple). Un SignedDataVerifier est lié à un environnement : un par environnement.
    Sans identifiant App Store (APPLE_APP_ID), que la bibliothèque exige en production, la sandbox seule."""

    def __init__(self, config):
        from appstoreserverlibrary.models.Environment import Environment
        from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier

        racines = [p.read_bytes() for p in sorted(Path(config.apple_racines).glob("*.cer"))]
        if not racines:
            raise ValueError(f"aucun certificat racine Apple dans {config.apple_racines!r}")
        envs = [Environment.PRODUCTION, Environment.SANDBOX] if config.apple_app_id else [Environment.SANDBOX]
        self._verificateurs = [SignedDataVerifier(racines, False, env, config.apns_bundle, config.apple_app_id or None) for env in envs]

    def verifier(self, jws: str) -> Transaction:
        from appstoreserverlibrary.signed_data_verifier import VerificationException, VerificationStatus

        for verificateur in self._verificateurs:
            try:
                t = verificateur.verify_and_decode_signed_transaction(jws)
                break
            except VerificationException as e:
                if e.status != VerificationStatus.INVALID_ENVIRONMENT:
                    raise ValueError(f"transaction refusée : {e.status.name}") from None
            except (ValueError, TypeError) as e:
                raise ValueError(f"transaction refusée : {type(e).__name__}") from None
        else:
            raise ValueError("transaction refusée : environnement inconnu")
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
        """Enregistre une transaction App Store pour le compte. 400 signifie seulement un refus définitif
        (transaction absente ou à la signature invalide, produit ou app inconnus, révoquée, transaction d'un
        autre compte jamais vue par le relais) : l'app jette alors la transaction. Toute autre erreur (401,
        429, 5xx, réseau) est passagère : l'app garde la transaction et la représente plus tard."""
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
        base = request.app.state.base
        connue = base.execute("select 1 from comptes where transaction_origine = ?", (t.origine,)).fetchone()
        if not connue and t.app_account_token and t.app_account_token.lower() != jeton_de_compte(compte):
            raise HTTPException(400, "transaction d'un autre compte")
        # L'ancien compte d'abord, pour l'index unique ; interrompu entre les deux, l'app représente la transaction.
        base.execute("update comptes set abonne_jusqu_au = null, transaction_origine = null where transaction_origine = ? and id != ?",
                     (t.origine, compte))
        base.execute("update comptes set abonne_jusqu_au = ?, transaction_origine = ? where id = ?", (t.expire_le, t.origine, compte))
        return {"abonne_jusqu_au": t.expire_le}

    return r
