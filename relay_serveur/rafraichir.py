"""Réveil de l'iPhone à la demande, logique du récepteur v1 : grâce si la synchro est récente, un seul réveil
à la fois par compte, budget horaire, attente d'un nouvel etat.json, jamais bloqué par une exception."""

import sqlite3
import threading
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .abonnement import abonne_requis
from .comptes import compte_courant

ENVS = ("sandbox", "production")


class Rafraichisseur:
    def __init__(self, base: sqlite3.Connection, envoyeur, config, attente: float = 25.0):
        self.base, self.envoyeur, self.config, self.attente = base, envoyeur, config, attente
        self.grace = 120.0
        self._verrou = threading.Lock()
        self._en_cours: dict[str, dict] = {}

    def _maj_etat(self, compte: str) -> float | None:
        ligne = self.base.execute("select maj from blobs where compte = ? and nom = 'etat.json'", (compte,)).fetchone()
        return ligne[0] if ligne else None

    def rafraichir(self, compte: str, maintenant: float) -> tuple[int, dict]:
        maj = self._maj_etat(compte)
        if maj is not None and maintenant - maj < self.grace:
            return 200, {"rafraichi": False, "maj": maj, "status": "synchro récente"}
        with self._verrou:
            en_cours = self._en_cours.get(compte)
            meneur = en_cours is None
            if meneur:
                en_cours = self._en_cours[compte] = {"fini": threading.Event(), "resultat": None}
        if not meneur:
            en_cours["fini"].wait(self.attente + 1)
            return en_cours["resultat"] or (504, {"rafraichi": False, "maj": maj, "status": "pas de réponse"})
        resultat = (500, {"rafraichi": False, "maj": maj, "status": "erreur interne du réveil"})
        try:
            resultat = self._reveiller(compte, maintenant, maj)
        except Exception:  # un fichier corrompu ou une bibliothèque absente ne doit pas bloquer les réveils suivants
            pass
        finally:
            with self._verrou:
                en_cours["resultat"] = resultat
                en_cours["fini"].set()
                self._en_cours.pop(compte, None)
        return resultat

    def _reveiller(self, compte: str, maintenant: float, maj: float | None) -> tuple[int, dict]:
        self.base.execute("delete from reveils where compte = ? and quand < ?", (compte, maintenant - 3600))
        if self.base.execute("select count(*) from reveils where compte = ?", (compte,)).fetchone()[0] >= self.config.reveils_par_heure:
            return 429, {"rafraichi": False, "maj": maj, "status": "budget de réveils épuisé"}
        ligne = self.base.execute("select apns, apns_env from comptes where id = ?", (compte,)).fetchone()
        if not ligne or not ligne[0]:
            return 503, {"rafraichi": False, "maj": maj, "status": "aucun appareil enregistré"}
        code = self.envoyeur.envoyer(ligne[0], ligne[1] or "sandbox")
        if code == 410:
            self.base.execute("update comptes set apns = null, apns_env = null where id = ?", (compte,))
        if code != 200:
            return 502, {"rafraichi": False, "maj": maj, "status": f"APNs a répondu {code}"}
        self.base.execute("insert into reveils (compte, quand) values (?, ?)", (compte, maintenant))
        while time.time() - maintenant < self.attente:
            nouvelle = self._maj_etat(compte)
            if nouvelle is not None and nouvelle >= maintenant:
                return 200, {"rafraichi": True, "maj": nouvelle, "status": "rafraîchi"}
            time.sleep(0.5)
        return 504, {"rafraichi": False, "maj": self._maj_etat(compte), "status": "pas de réponse"}


def routeur(rafraichisseur: Rafraichisseur) -> APIRouter:
    r = APIRouter()

    @r.post("/appareil")
    def enregistrer_appareil(corps: dict, request: Request):
        compte = compte_courant(request)
        token, env = corps.get("token"), corps.get("env", "sandbox")
        if not isinstance(token, str) or not token or env not in ENVS:
            raise HTTPException(400, "token et env (sandbox ou production) attendus")
        request.app.state.base.execute("update comptes set apns = ?, apns_env = ? where id = ?", (token, env, compte))
        return {"status": "enregistré"}

    @r.post("/rafraichir")
    def rafraichir(request: Request):
        compte = abonne_requis(request)
        code, corps = rafraichisseur.rafraichir(compte, time.time())
        return JSONResponse(corps, status_code=code)

    return r
