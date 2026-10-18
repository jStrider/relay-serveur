"""Génère une fois pour toutes vecteurs/chiffrement.json : des clés et nonces tirés au sort puis figés dans le dépôt.
Ne pas relancer sans raison : l'app (Swift) et le client (Python) rejouent ces valeurs dans leurs tests."""

import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ID = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CAS = [
    ("vide", "etat.json", b""),
    ("json_court", "metriques/step_count/2026-10.json", b'{"name": "step_count", "units": "count", "data": [{"date": "2026-10-18 00:00:00 +0200", "qty": 14040, "source": ""}]}'),
    ("100ko", "seances/2026-10-18-ABCDEF.json", (b'{"route": [' + b"[43.6, 3.87, 12.0, 1792333457.0], " * 4000)[:100 * 1024 - 1] + b"]"),
]

vecteurs = []
for nom, blob, clair in CAS:
    cle, nonce = os.urandom(32), os.urandom(12)
    chiffre = AESGCM(cle).encrypt(nonce, clair, (ID + blob).encode())
    vecteurs.append({"nom": nom, "cle": cle.hex(), "id": ID, "blob": blob, "nonce": nonce.hex(), "clair": clair.hex(),
                     "chiffre": chiffre.hex(), "blob_chiffre": (nonce + chiffre).hex()})
Path(__file__).parent.parent.joinpath("vecteurs", "chiffrement.json").write_text(json.dumps(vecteurs, indent=1))
print(f"{len(vecteurs)} vecteurs écrits")
