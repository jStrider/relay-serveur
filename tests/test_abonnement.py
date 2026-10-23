import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from relay_serveur.abonnement import VerificateurApple
from relay_serveur.app import creer_app
from tests.test_blobs import deposer
from tests.test_comptes import ID, JETON, creer, entete


from relay_serveur.abonnement import Transaction, jeton_de_compte


class FauxVerificateur:
    def __init__(self, expire_le=None):
        self.expire = expire_le
        self.revoquee = False
        self.app_account_token = None

    def verifier(self, jws):
        if not jws.startswith("jws-valide"):
            raise ValueError("signature invalide")
        return Transaction(expire_le=self.expire, origine="tx-" + jws, revoquee=self.revoquee, app_account_token=self.app_account_token)


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
        v.verifier("a.b.c")


def test_transaction_connue_deplacee_vers_le_nouveau_compte(serveur):
    """Phrase régénérée, compte supprimé, nouvel iPhone : l'abonnement suit le compte qui présente la transaction."""
    c, base, v = serveur
    creer(c, id="B" * 26, jeton="b" * 43)
    v.app_account_token = jeton_de_compte(ID)  # posé à l'achat par le compte d'origine
    assert c.post("/abonnement", json={"transaction": "jws-valide"}, headers=entete()).status_code == 200
    r = c.post("/abonnement", json={"transaction": "jws-valide"}, headers=entete("b" * 43))
    assert r.status_code == 200
    assert base.execute("select abonne_jusqu_au, transaction_origine from comptes where id = ?", ("B" * 26,)).fetchone() == (v.expire, "tx-jws-valide")
    assert base.execute("select abonne_jusqu_au, transaction_origine from comptes where id = ?", (ID,)).fetchone() == (None, None)
    assert deposer(c, "prevu.json").status_code == 402


def test_transaction_inconnue_d_un_autre_compte_refusee(serveur):
    c, base, v = serveur
    creer(c, id="B" * 26, jeton="b" * 43)
    v.app_account_token = jeton_de_compte(ID)
    assert c.post("/abonnement", json={"transaction": "jws-valide"}, headers=entete("b" * 43)).status_code == 400
    assert base.execute("select abonne_jusqu_au from comptes where id = ?", ("B" * 26,)).fetchone()[0] is None


def test_renouvellement_meme_compte_accepte(serveur):
    c, base, v = serveur
    assert c.post("/abonnement", json={"transaction": "jws-valide"}, headers=entete()).status_code == 200
    v.expire += 30 * 86400
    assert c.post("/abonnement", json={"transaction": "jws-valide"}, headers=entete()).status_code == 200


def test_transaction_revoquee_400(serveur):
    c, base, v = serveur
    v.revoquee = True
    assert c.post("/abonnement", json={"transaction": "jws-valide"}, headers=entete()).status_code == 400
    assert deposer(c, "prevu.json").status_code == 402


def test_app_account_token_doit_correspondre_au_compte(serveur):
    c, base, v = serveur
    v.app_account_token = jeton_de_compte("B" * 26)
    assert c.post("/abonnement", json={"transaction": "jws-valide"}, headers=entete()).status_code == 400
    v.app_account_token = jeton_de_compte(ID)
    assert c.post("/abonnement", json={"transaction": "jws-valide"}, headers=entete()).status_code == 200


class FauxSignedDataVerifier:
    """Remplace SignedDataVerifier : lié à un environnement, comme lui."""

    def __init__(self, environnement, transaction):
        self.environnement, self.transaction, self.appels = environnement, transaction, 0

    def verify_and_decode_signed_transaction(self, jws):
        from appstoreserverlibrary.signed_data_verifier import VerificationException, VerificationStatus

        self.appels += 1
        if jws == "jws-signature-invalide":
            raise VerificationException(VerificationStatus.VERIFICATION_FAILURE)
        if jws != "jws-" + self.environnement:
            raise VerificationException(VerificationStatus.INVALID_ENVIRONMENT)
        return self.transaction


@pytest.fixture
def verificateur_apple(config):
    from types import SimpleNamespace

    config.apple_racines = str(Path(__file__).parent.parent / "deploy" / "apple")
    config.apns_bundle = "fr.exemple.relay"
    config.apple_app_id = 123456
    v = VerificateurApple(config)
    t = SimpleNamespace(expiresDate=2_000_000_000_000, originalTransactionId=42, revocationDate=None, appAccountToken=None)
    v._verificateurs = [FauxSignedDataVerifier("production", t), FauxSignedDataVerifier("sandbox", t)]
    return v


def test_verificateur_apple_production_puis_sandbox(verificateur_apple):
    production, sandbox = verificateur_apple._verificateurs
    assert verificateur_apple.verifier("jws-production").origine == "42"
    assert sandbox.appels == 0
    assert verificateur_apple.verifier("jws-sandbox").expire_le == 2_000_000_000  # TestFlight, relecteur Apple
    assert (production.appels, sandbox.appels) == (2, 1)


def test_verificateur_apple_signature_invalide_sans_essayer_la_sandbox(verificateur_apple):
    with pytest.raises(ValueError):
        verificateur_apple.verifier("jws-signature-invalide")
    assert verificateur_apple._verificateurs[1].appels == 0


def test_verificateur_apple_deux_environnements(config):
    from appstoreserverlibrary.models.Environment import Environment

    config.apple_racines = str(Path(__file__).parent.parent / "deploy" / "apple")
    config.apns_bundle = "fr.exemple.relay"
    config.apple_app_id = 123456
    assert [v._environment for v in VerificateurApple(config)._verificateurs] == [Environment.PRODUCTION, Environment.SANDBOX]
    config.apple_app_id = 0  # pas encore d'identifiant App Store : la sandbox seule
    assert [v._environment for v in VerificateurApple(config)._verificateurs] == [Environment.SANDBOX]


def test_jeton_de_compte_stable_et_uuid():
    import uuid
    assert jeton_de_compte(ID) == jeton_de_compte(ID)
    uuid.UUID(jeton_de_compte(ID))
