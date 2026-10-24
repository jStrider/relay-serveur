"""Messages de l'agent vers l'iPhone : chiffrés par l'agent, jamais stockés, transmis à APNs en notification visible.
Le relais n'en voit que la taille ; l'extension de notification de l'app les déchiffre à l'arrivée."""

import re
import time

from fastapi import APIRouter, HTTPException, Request

from .abonnement import abonne_requis

MAX_CHIFFRE = 3000  # base64url ; APNs refuse au-delà de 4 Ko de charge


def routeur(envoyeur) -> APIRouter:
    r = APIRouter()

    @r.post("/messages")
    def envoyer(corps: dict, request: Request):
        compte = abonne_requis(request)
        chiffre = corps.get("chiffre")
        if not isinstance(chiffre, str) or not re.fullmatch(r"[A-Za-z0-9_-]{40,%d}" % MAX_CHIFFRE, chiffre):
            raise HTTPException(400, f"chiffre attendu : base64url, {MAX_CHIFFRE} caractères au plus")
        base, maintenant = request.app.state.base, time.time()
        base.execute("delete from messages where compte = ? and quand < ?", (compte, maintenant - 3600))
        if base.execute("select count(*) from messages where compte = ?", (compte,)).fetchone()[0] >= request.app.state.config.messages_par_heure:
            raise HTTPException(429, "trop de messages cette heure-ci")
        ligne = base.execute("select apns, apns_env from comptes where id = ?", (compte,)).fetchone()
        if not ligne or not ligne[0]:
            raise HTTPException(503, "aucun appareil enregistré")
        code = envoyeur.alerter(ligne[0], ligne[1] or "sandbox", chiffre)
        if code == 410:
            base.execute("update comptes set apns = null, apns_env = null where id = ?", (compte,))
        if code != 200:
            raise HTTPException(502, f"APNs a répondu {code}")
        base.execute("insert into messages (compte, quand) values (?, ?)", (compte, maintenant))
        return {"status": "envoyé"}

    return r
