"""Génère une fois vecteurs/appairage.json : clés X25519 tirées au sort puis figées. Ne pas relancer sans raison :
le client Python et le paquet Swift rejouent ces valeurs."""

import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SESSION = "K7Q2M6XA"
PHRASE = "relay1:ABCDEFGHIJKLMNOPQRSTUVWXYZ:" + "a" * 43 + ":AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"

agent, app = X25519PrivateKey.generate(), X25519PrivateKey.generate()
secret = agent.exchange(app.public_key())
hk = lambda info, n: HKDF(algorithm=hashes.SHA256(), length=n, salt=SESSION.encode(), info=info.encode()).derive(secret)  # noqa: E731
cle = hk("relay-appairage-cle", 32)
code = int.from_bytes(hk("relay-appairage-code", 4), "big") % 1_000_000
nonce = os.urandom(12)
chiffre = nonce + AESGCM(cle).encrypt(nonce, PHRASE.encode(), SESSION.encode())
v = {"session": SESSION, "privee_agent": agent.private_bytes_raw().hex(), "publique_agent": agent.public_key().public_bytes_raw().hex(),
     "privee_app": app.private_bytes_raw().hex(), "publique_app": app.public_key().public_bytes_raw().hex(),
     "cle": cle.hex(), "code": f"{code:06d}", "phrase": PHRASE, "nonce": nonce.hex(), "identite_chiffree": chiffre.hex()}
Path(__file__).parent.parent.joinpath("vecteurs", "appairage.json").write_text(json.dumps(v, indent=1))
print("vecteur écrit, code", v["code"])
