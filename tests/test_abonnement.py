import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from relay_serveur.abonnement import VerificateurApple
from relay_serveur.app import creer_app
from tests.test_blobs import deposer
from tests.test_comptes import ID, JETON, creer, entete


class FauxVerificateur:
    def __init__(self, expire_le=None):
        self.expire = expire_le

    def expire_le(self, jws):
        if jws != "jws-valide":
            raise ValueError("signature invalide")
        return self.expire


@pytest.fixture
def serveur(config, base_tmp):
    v = FauxVerificateur(expire_le=time.time() + 30 * 86400)
    c = TestClient(creer_app(config, base_tmp, verificateur=v))
    creer(c)
    return c, base_tmp, v


def test_transaction_valide_met_a_jour(serveur):
    c, base, v = serveur
    r = c.post("/abonnement", json={"transaction": "jws-valide"}, headers=entete())
    assert r.status_code == 200 and abs(r.json()["abonne_jusqu_au"] - v.expire) < 1
    assert deposer(c, "prevu.json").status_code == 200


def test_transaction_invalide_400_et_inchange(serveur):
    c, base, v = serveur
    assert c.post("/abonnement", json={"transaction": "a.b.c"}, headers=entete()).status_code == 400
    assert base.execute("select abonne_jusqu_au from comptes where id = ?", (ID,)).fetchone()[0] is None
    assert deposer(c, "prevu.json").status_code == 402


def test_abonnement_expire_402_sur_prevu(serveur):
    c, base, v = serveur
    v.expire = time.time() - 60
    assert c.post("/abonnement", json={"transaction": "jws-valide"}, headers=entete()).status_code == 200
    assert deposer(c, "prevu.json").status_code == 402


def test_gratuit_ignore_l_abonnement(config, base_tmp):
    config.gratuit = True
    c = TestClient(creer_app(config, base_tmp, verificateur=FauxVerificateur()))
    creer(c)
    assert deposer(c, "prevu.json").status_code == 200


def test_verificateur_apple_rejette_un_jws_bidon(config):
    config.apple_racines = str(Path(__file__).parent.parent / "deploy" / "apple")
    config.apns_bundle = "fr.exemple.relay"
    config.apple_app_id = 123456
    v = VerificateurApple(config)
    with pytest.raises(ValueError):
        v.expire_le("a.b.c")
