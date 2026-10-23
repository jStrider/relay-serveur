import hashlib
import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

V = json.loads((Path(__file__).parent.parent / "vecteurs" / "appairage.json").read_text())


def hkdf(secret, session, info, n):
    return HKDF(algorithm=hashes.SHA256(), length=n, salt=session.encode(), info=info.encode()).derive(secret)


def test_vecteur_rejoue():
    agent = X25519PrivateKey.from_private_bytes(bytes.fromhex(V["privee_agent"]))
    app = X25519PrivateKey.from_private_bytes(bytes.fromhex(V["privee_app"]))
    assert agent.public_key().public_bytes_raw().hex() == V["publique_agent"]
    assert app.public_key().public_bytes_raw().hex() == V["publique_app"]
    secret_agent = agent.exchange(X25519PublicKey.from_public_bytes(bytes.fromhex(V["publique_app"])))
    secret_app = app.exchange(X25519PublicKey.from_public_bytes(bytes.fromhex(V["publique_agent"])))
    assert secret_agent == secret_app
    cle = hkdf(secret_agent, V["session"], "relay-appairage-cle", 32)
    assert cle.hex() == V["cle"]
    code = int.from_bytes(hkdf(secret_agent, V["session"], "relay-appairage-code", 4), "big") % 1_000_000
    assert f"{code:06d}" == V["code"]
    nonce = bytes.fromhex(V["nonce"])
    chiffre = nonce + AESGCM(cle).encrypt(nonce, V["phrase"].encode(), V["session"].encode())
    assert chiffre.hex() == V["identite_chiffree"]
    assert AESGCM(cle).decrypt(nonce, chiffre[12:], V["session"].encode()).decode() == V["phrase"]


def test_engagement_est_le_hache_de_la_cle_agent():
    assert hashlib.sha256(bytes.fromhex(V["publique_agent"])).hexdigest() == V["engagement"]


def test_aad_autre_session_refusee():
    cle, blob = bytes.fromhex(V["cle"]), bytes.fromhex(V["identite_chiffree"])
    with pytest.raises(InvalidTag):
        AESGCM(cle).decrypt(blob[:12], blob[12:], b"AUTRESES")


def test_code_six_chiffres_et_session_valide():
    assert len(V["code"]) == 6 and V["code"].isdigit()
    assert len(V["session"]) == 8 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in V["session"])
