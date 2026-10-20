"""Appairage par code court : sessions éphémères où l'agent et l'app échangent leurs clés publiques X25519,
puis où l'app dépose la phrase chiffrée pour l'agent. Le relais ne voit que des clés publiques et du chiffré.
Aucune authentification : l'agent n'a pas encore de jeton ; la comparaison des codes des deux côtés détecte
tout intrus, et les sessions vivent dix minutes."""

import base64
import os
import re
import sqlite3
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
DUREE = 10 * 60
MAX_CORPS = 4 * 1024


def nouvelle_session() -> str:
    return "".join(ALPHABET[b % 32] for b in os.urandom(8))


def normaliser(saisie: str) -> str | None:
    """« k7q2-m9xa » → « K7Q2M9XA » ; None si ce n'est pas une session."""
    s = saisie.replace("-", "").replace(" ", "").upper()
    return s if re.fullmatch(r"[A-Z2-7]{8}", s) else None


def cle_publique_valide(texte) -> bool:
    if not isinstance(texte, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", texte):
        return False
    try:
        return len(base64.urlsafe_b64decode(texte + "=")) == 32
    except ValueError:
        return False


def purger(base: sqlite3.Connection, avant: float) -> int:
    return base.execute("delete from appairages where cree_le < ?", (avant,)).rowcount


def _lire(base: sqlite3.Connection, session: str):
    ligne = base.execute("select cle_agent, cle_app, identite, cree_le from appairages where session = ?", (session,)).fetchone()
    if ligne is None or ligne[3] < time.time() - DUREE:
        raise HTTPException(404, "session d'appairage inconnue ou expirée")
    return ligne


def routeur() -> APIRouter:
    r = APIRouter()
    creations: dict[str, deque] = defaultdict(deque)

    async def corps_json(request: Request) -> dict:
        brut = await request.body()
        if len(brut) > MAX_CORPS:
            raise HTTPException(413, "corps trop gros")
        try:
            import json
            d = json.loads(brut or b"{}")
        except ValueError:
            raise HTTPException(400, "JSON attendu")
        return d if isinstance(d, dict) else {}

    def session_ou_404(saisie: str) -> str:
        s = normaliser(saisie)
        if s is None:
            raise HTTPException(404, "session d'appairage inconnue ou expirée")
        return s

    @r.post("/appairages", status_code=201)
    async def ouvrir(request: Request):
        ip = request.client.host if request.client else "?"
        recents, now = creations[ip], time.time()
        while recents and recents[0] < now - 3600:
            recents.popleft()
        if len(recents) >= request.app.state.config.creations_par_heure_ip:
            raise HTTPException(429, "trop d'appairages depuis cette adresse")
        corps = await corps_json(request)
        if not cle_publique_valide(corps.get("cle_publique_agent")):
            raise HTTPException(400, "cle_publique_agent attendue : 32 octets en base64url")
        base = request.app.state.base
        session = nouvelle_session()
        base.execute("insert into appairages (session, cle_agent, cree_le) values (?, ?, ?)", (session, corps["cle_publique_agent"], now))
        recents.append(now)
        return {"session": session}

    @r.get("/appairages/{saisie}")
    def lire(saisie: str, request: Request):
        s = session_ou_404(saisie)
        cle_agent, cle_app, identite, _ = _lire(request.app.state.base, s)
        return {"cle_publique_agent": cle_agent, "cle_publique_app": cle_app, "identite_chiffree": identite}

    @r.put("/appairages/{saisie}/app")
    async def publier_cle_app(saisie: str, request: Request):
        s = session_ou_404(saisie)
        base = request.app.state.base
        _, cle_app, _, _ = _lire(base, s)
        corps = await corps_json(request)
        if not cle_publique_valide(corps.get("cle_publique_app")):
            raise HTTPException(400, "cle_publique_app attendue : 32 octets en base64url")
        if cle_app is not None:
            raise HTTPException(409, "la clé de l'app est déjà posée")  # un tiers ne remplace pas la première venue
        base.execute("update appairages set cle_app = ? where session = ?", (corps["cle_publique_app"], s))
        return {"status": "posée"}

    @r.put("/appairages/{saisie}/identite")
    async def deposer_identite(saisie: str, request: Request):
        s = session_ou_404(saisie)
        base = request.app.state.base
        _lire(base, s)
        corps = await corps_json(request)
        identite = corps.get("identite_chiffree")
        if not isinstance(identite, str) or not identite or not re.fullmatch(r"[A-Za-z0-9_-]+", identite):
            raise HTTPException(400, "identite_chiffree attendue en base64url")
        base.execute("update appairages set identite = ? where session = ?", (identite, s))
        return {"status": "déposée"}

    @r.delete("/appairages/{saisie}", status_code=204)
    def fermer(saisie: str, request: Request):
        s = session_ou_404(saisie)
        base = request.app.state.base
        _lire(base, s)
        base.execute("delete from appairages where session = ?", (s,))

    return r
