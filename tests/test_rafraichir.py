import threading
import time

import pytest
from fastapi.testclient import TestClient

from relay_serveur import blobs
from relay_serveur.app import creer_app
from relay_serveur.rafraichir import Rafraichisseur
from tests.test_comptes import ID, JETON, creer, entete


class FauxEnvoyeur:
    def __init__(self, code=200):
        self.code, self.appels = code, []

    def envoyer(self, token, env):
        self.appels.append((token, env))
        return self.code


@pytest.fixture
def monde(config, base_tmp):
    """Serveur gratuit avec un compte et un appareil enregistré, faux APNs injecté."""
    config.gratuit = True
    envoyeur = FauxEnvoyeur()
    c = TestClient(creer_app(config, base_tmp, envoyeur=envoyeur))
    creer(c)
    assert c.post("/appareil", json={"token": "abc123", "env": "sandbox"}, headers=entete()).status_code == 200
    return c, base_tmp, envoyeur, Rafraichisseur(base_tmp, envoyeur, config, attente=3)


def synchro_dans(base, delai):
    threading.Timer(delai, lambda: blobs.deposer(base, ID, "etat.json", b"{}")).start()


def test_synchro_recente_sans_reveil(monde):
    c, base, envoyeur, r = monde
    blobs.deposer(base, ID, "etat.json", b"{}")
    code, corps = r.rafraichir(ID, time.time())
    assert (code, corps["rafraichi"]) == (200, False) and envoyeur.appels == []


def test_sans_appareil_503(monde):
    c, base, envoyeur, r = monde
    base.execute("update comptes set apns = null")
    assert r.rafraichir(ID, time.time())[0] == 503


def test_reveil_puis_etat_200(monde):
    c, base, envoyeur, r = monde
    synchro_dans(base, 0.3)
    code, corps = r.rafraichir(ID, time.time())
    assert (code, corps["rafraichi"], envoyeur.appels) == (200, True, [("abc123", "sandbox")])


def test_pas_de_reponse_504(monde):
    c, base, envoyeur, r = monde
    r.attente = 0.6
    code, corps = r.rafraichir(ID, time.time())
    assert (code, corps["status"]) == (504, "pas de réponse")


def test_apns_410_oublie_l_appareil_502(monde):
    c, base, envoyeur, r = monde
    envoyeur.code = 410
    assert r.rafraichir(ID, time.time())[0] == 502
    assert base.execute("select apns from comptes where id = ?", (ID,)).fetchone()[0] is None


def test_budget_6_par_heure_429(monde):
    c, base, envoyeur, r = monde
    r.attente = 0.05
    for _ in range(6):
        assert r.rafraichir(ID, time.time())[0] == 504
    assert r.rafraichir(ID, time.time())[0] == 429
    assert len(envoyeur.appels) == 6


def test_deux_appels_simultanes_un_seul_reveil(monde):
    c, base, envoyeur, r = monde
    resultats = []
    fils = [threading.Thread(target=lambda: resultats.append(r.rafraichir(ID, time.time()))) for _ in range(2)]
    for f in fils:
        f.start()
    synchro_dans(base, 0.4)
    for f in fils:
        f.join()
    assert [x[0] for x in resultats] == [200, 200] and len(envoyeur.appels) == 1


def test_exception_ne_bloque_pas_les_suivants(monde):
    c, base, envoyeur, r = monde
    original = r._reveiller
    r._reveiller = lambda *a: (_ for _ in ()).throw(RuntimeError("boum"))
    assert r.rafraichir(ID, time.time())[0] == 500
    r._reveiller = original
    synchro_dans(base, 0.3)
    assert r.rafraichir(ID, time.time())[0] == 200


def test_env_sandbox_transmis_a_l_envoyeur(monde):
    c, base, envoyeur, r = monde
    c.post("/appareil", json={"token": "def456", "env": "production"}, headers=entete())
    r.attente = 0.05
    r.rafraichir(ID, time.time())
    assert envoyeur.appels == [("def456", "production")]


def test_route_rafraichir_et_non_abonne_402(config, base_tmp):
    envoyeur = FauxEnvoyeur()
    c = TestClient(creer_app(config, base_tmp, envoyeur=envoyeur))
    creer(c)
    assert c.post("/rafraichir", headers=entete()).status_code == 402
    config.gratuit = True
    blobs.deposer(base_tmp, ID, "etat.json", b"{}")
    r = c.post("/rafraichir", headers=entete())
    assert r.status_code == 200 and r.json()["rafraichi"] is False


def test_appareil_env_inconnu_400(monde):
    c, *_ = monde
    assert c.post("/appareil", json={"token": "x", "env": "lune"}, headers=entete()).status_code == 400
