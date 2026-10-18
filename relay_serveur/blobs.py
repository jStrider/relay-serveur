"""Blobs : des octets opaques, nommés par type et période, isolés par compte, bornés par des quotas."""

import re
import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .abonnement import abonne_requis
from .comptes import compte_courant

NOM_RE = re.compile(r"^(metriques/[a-z_]+/\d{4}-\d{2}\.json|seances/\d{4}-\d{2}-\d{2}-[A-Za-z0-9-]+\.json|etat\.json|prevu\.json)$")


def nom_valide(nom: str) -> bool:
    return bool(NOM_RE.match(nom))


def deposer(base: sqlite3.Connection, compte: str, nom: str, contenu: bytes) -> float:
    maj = time.time()
    base.execute("insert into blobs (compte, nom, contenu, taille, maj) values (?, ?, ?, ?, ?) "
                 "on conflict(compte, nom) do update set contenu = excluded.contenu, taille = excluded.taille, maj = excluded.maj",
                 (compte, nom, contenu, len(contenu), maj))
    return maj


def lister(base: sqlite3.Connection, compte: str, depuis: float | None = None) -> list[dict]:
    lignes = base.execute("select nom, taille, maj from blobs where compte = ? and maj >= ? order by nom", (compte, depuis or 0))
    return [{"nom": n, "taille": t, "maj": m} for n, t, m in lignes]


def lire(base: sqlite3.Connection, compte: str, nom: str) -> bytes | None:
    ligne = base.execute("select contenu from blobs where compte = ? and nom = ?", (compte, nom)).fetchone()
    return bytes(ligne[0]) if ligne else None


def retirer(base: sqlite3.Connection, compte: str, nom: str) -> bool:
    return base.execute("delete from blobs where compte = ? and nom = ?", (compte, nom)).rowcount > 0


def usage(base: sqlite3.Connection, compte: str) -> tuple[int, int]:
    nombre, octets = base.execute("select count(*), coalesce(sum(taille), 0) from blobs where compte = ?", (compte,)).fetchone()
    return nombre, octets


def routeur() -> APIRouter:
    r = APIRouter()

    def verifier_nom(nom: str) -> str:
        if not nom_valide(nom):
            raise HTTPException(400, "nom de blob refusé")
        return nom

    @r.put("/blobs/{nom:path}")
    async def deposer_blob(nom: str, request: Request):
        verifier_nom(nom)
        compte = abonne_requis(request) if nom == "prevu.json" else compte_courant(request)
        config, base = request.app.state.config, request.app.state.base
        contenu = await request.body()
        if len(contenu) > config.max_blob:
            raise HTTPException(413, "blob trop gros")
        nombre, octets = usage(base, compte)
        existant = base.execute("select taille from blobs where compte = ? and nom = ?", (compte, nom)).fetchone()
        if existant is None and nombre >= config.max_blobs:
            raise HTTPException(507, "trop de blobs pour ce compte")
        if octets - (existant[0] if existant else 0) + len(contenu) > config.max_octets:
            raise HTTPException(507, "quota d'octets dépassé pour ce compte")
        return {"maj": deposer(base, compte, nom, contenu)}

    @r.get("/blobs")
    def lister_blobs(request: Request, depuis: float | None = None):
        return lister(request.app.state.base, compte_courant(request), depuis)

    @r.get("/blobs/{nom:path}")
    def lire_blob(nom: str, request: Request):
        verifier_nom(nom)
        contenu = lire(request.app.state.base, compte_courant(request), nom)
        if contenu is None:
            raise HTTPException(404, "blob absent")
        return Response(content=contenu, media_type="application/octet-stream")

    @r.delete("/blobs/{nom:path}", status_code=204)
    def retirer_blob(nom: str, request: Request):
        verifier_nom(nom)
        if not retirer(request.app.state.base, compte_courant(request), nom):
            raise HTTPException(404, "blob absent")

    return r
