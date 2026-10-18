"""Comptes : un identifiant public et un jeton dont seul le hachage SHA-256 est gardé et indexé."""

import hashlib
import re
import sqlite3
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request

ID_RE = re.compile(r"^[A-Z2-7]{26}$")  # base32 sans remplissage
JETON_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")  # 32 octets en base64url sans remplissage


def hacher(jeton: str) -> bytes:
    return hashlib.sha256(jeton.encode()).digest()


def creer(base: sqlite3.Connection, id: str, jeton: str) -> bool:
    """False si l'identifiant existe déjà."""
    now = time.time()
    try:
        base.execute("insert into comptes (id, jeton_hache, cree_le, vu_le) values (?, ?, ?, ?)", (id, hacher(jeton), now, now))
    except sqlite3.IntegrityError:
        return False
    return True


def authentifier(base: sqlite3.Connection, entete: str | None) -> str | None:
    """Identifiant du compte si l'en-tête Authorization porte un jeton valide ; met à jour vu_le."""
    if not entete or not entete.startswith("Bearer "):
        return None
    jeton = entete[7:].strip()
    if not JETON_RE.match(jeton):
        return None
    # Recherche directe sur le hachage : un SHA-256 d'un jeton aléatoire de 256 bits n'offre aucune prise au chronométrage.
    ligne = base.execute("select id from comptes where jeton_hache = ?", (hacher(jeton),)).fetchone()
    if ligne is None:
        return None
    base.execute("update comptes set vu_le = ? where id = ?", (time.time(), ligne[0]))
    return ligne[0]


def supprimer(base: sqlite3.Connection, id: str) -> None:
    base.execute("delete from comptes where id = ?", (id,))  # blobs et réveils suivent (on delete cascade)


def purger_inactifs(base: sqlite3.Connection, avant: float) -> int:
    return base.execute("delete from comptes where vu_le < ?", (avant,)).rowcount


def compte_courant(request: Request) -> str:
    """Dépendance FastAPI : l'identifiant du compte authentifié, sinon 401. Le middleware de débit a déjà
    authentifié la requête et posé request.state.compte : on ne refait pas la recherche."""
    id = getattr(request.state, "compte", None)
    if id is None and not getattr(request.state, "authentifie", False):
        id = authentifier(request.app.state.base, request.headers.get("Authorization"))
    if id is None:
        raise HTTPException(401, "jeton invalide")
    return id


def routeur() -> APIRouter:
    r = APIRouter()
    creations: dict[str, deque] = defaultdict(deque)

    @r.post("/comptes", status_code=201)
    def creer_compte(corps: dict, request: Request):
        config = request.app.state.config
        ip = request.client.host if request.client else "?"
        recents = creations[ip]
        now = time.time()
        while recents and recents[0] < now - 3600:
            recents.popleft()
        if len(recents) >= config.creations_par_heure_ip:
            raise HTTPException(429, "trop de créations depuis cette adresse")
        id, jeton = corps.get("id"), corps.get("jeton")
        if not isinstance(id, str) or not ID_RE.match(id) or not isinstance(jeton, str) or not JETON_RE.match(jeton):
            raise HTTPException(400, "id (base32, 26 caractères) et jeton (base64url, 43 caractères) attendus")
        if not creer(request.app.state.base, id, jeton):
            raise HTTPException(409, "identifiant déjà pris")
        recents.append(now)
        return {"status": "créé"}

    @r.delete("/comptes/moi", status_code=204)
    def supprimer_compte(request: Request):
        supprimer(request.app.state.base, compte_courant(request))

    return r
