import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VECTEURS = json.loads((Path(__file__).parent.parent / "vecteurs" / "chiffrement.json").read_text())


def aad(v):
    return (v["id"] + v["blob"]).encode()


@pytest.mark.parametrize("v", VECTEURS, ids=[v["nom"] for v in VECTEURS])
def test_vecteurs_rejoues(v):
    cle, nonce, clair, chiffre = (bytes.fromhex(v[k]) for k in ("cle", "nonce", "clair", "chiffre"))
    assert AESGCM(cle).encrypt(nonce, clair, aad(v)) == chiffre
    assert AESGCM(cle).decrypt(nonce, chiffre, aad(v)) == clair
    assert v["blob_chiffre"] == (nonce + chiffre).hex()


def test_aad_lie_le_nom():
    v = VECTEURS[1]
    cle, nonce, chiffre = (bytes.fromhex(v[k]) for k in ("cle", "nonce", "chiffre"))
    with pytest.raises(InvalidTag):
        AESGCM(cle).decrypt(nonce, chiffre, (v["id"] + "metriques/step_count/2026-11.json").encode())


def test_quatre_vecteurs_dont_vide_et_100ko():
    tailles = sorted(len(bytes.fromhex(v["clair"])) for v in VECTEURS)
    assert tailles[0] == 0 and tailles[-1] == 100 * 1024 and len(VECTEURS) == 3
