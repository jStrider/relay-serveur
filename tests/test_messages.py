import pytest
from fastapi.testclient import TestClient

from relay_serveur.app import creer_app
from tests.test_comptes import creer, entete

CHIFFRE = "A" * 60


class FauxEnvoyeur:
    def __init__(self, code=200):
        self.code, self.alertes = code, []

    def envoyer(self, token, env):
        return self.code

    def alerter(self, token, env, chiffre):
        self.alertes.append((token, env, chiffre))
        return self.code


@pytest.fixture
def monde(config, base_tmp):
    envoyeur = FauxEnvoyeur()
    c = TestClient(creer_app(config, base_tmp, envoyeur=envoyeur))
    creer(c)
    c.post("/appareil", json={"token": "abc123", "env": "production"}, headers=entete())
    base_tmp.execute("update comptes set abonne_jusqu_au = 4102444800")
    return c, base_tmp, envoyeur


def test_message_transmis_sans_etre_garde(monde):
    c, base, envoyeur = monde
    assert c.post("/messages", json={"chiffre": CHIFFRE}, headers=entete()).status_code == 200
    assert envoyeur.alertes == [("abc123", "production", CHIFFRE)]
    assert base.execute("select count(*) from blobs").fetchone()[0] == 0


def test_sans_abonnement_402(monde):
    c, base, envoyeur = monde
    base.execute("update comptes set abonne_jusqu_au = null")
    assert c.post("/messages", json={"chiffre": CHIFFRE}, headers=entete()).status_code == 402
    assert envoyeur.alertes == []


def test_chiffre_mal_forme_ou_trop_long_400(monde):
    c, base, envoyeur = monde
    for chiffre in (None, "court", "A" * 3001, "A" * 50 + "/+"):
        assert c.post("/messages", json={"chiffre": chiffre}, headers=entete()).status_code == 400


def test_budget_horaire_429(monde, config):
    c, base, envoyeur = monde
    config.messages_par_heure = 2
    codes = [c.post("/messages", json={"chiffre": CHIFFRE}, headers=entete()).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_sans_appareil_503_et_jeton_perime_efface(monde):
    c, base, envoyeur = monde
    envoyeur.code = 410
    assert c.post("/messages", json={"chiffre": CHIFFRE}, headers=entete()).status_code == 502
    assert base.execute("select apns from comptes").fetchone()[0] is None
    assert c.post("/messages", json={"chiffre": CHIFFRE}, headers=entete()).status_code == 503
