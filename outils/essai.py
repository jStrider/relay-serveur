"""Essai de bout en bout contre un relais : crée un compte, dépose deux blobs chiffrés, les relit et les déchiffre,
constate qu'un octet altéré est refusé, que prevu.json exige l'abonnement, et que le compte supprimé répond 401.
Usage : uv run python outils/essai.py https://relay.<zone>   (ou http://127.0.0.1:8780 en local)"""

import base64
import json
import os
import sys
from pathlib import Path

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8780"
VECTEUR = json.loads((Path(__file__).parent.parent / "vecteurs" / "chiffrement.json").read_text())[1]


def main():
    id = base64.b32encode(os.urandom(16)).decode().rstrip("=")
    jeton = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
    cle = bytes.fromhex(VECTEUR["cle"])
    c = httpx.Client(base_url=URL, headers={"Authorization": f"Bearer {jeton}"}, timeout=30)

    r = httpx.post(f"{URL}/comptes", json={"id": id, "jeton": jeton}, timeout=30)
    assert r.status_code == 201, r.text
    print("compte créé", id)

    clair = b'{"name": "weight_body_mass", "data": [{"date": "2026-10-18 00:00:00 +0200", "qty": 95.7}]}'
    blobs = {"metriques/weight_body_mass/2026-10.json": clair, "etat.json": b'{"synced_at": "2026-10-18 20:00:00 +0200"}'}
    for nom, contenu in blobs.items():
        nonce = os.urandom(12)
        chiffre = nonce + AESGCM(cle).encrypt(nonce, contenu, (id + nom).encode())
        r = c.put(f"/blobs/{nom}", content=chiffre, headers={"Content-Type": "application/octet-stream"})
        assert r.status_code == 200, (nom, r.text)
    print("deux blobs déposés")

    liste = c.get("/blobs").json()
    assert {b["nom"] for b in liste} == set(blobs), liste
    for nom, contenu in blobs.items():
        recu = c.get(f"/blobs/{nom}").content
        assert AESGCM(cle).decrypt(recu[:12], recu[12:], (id + nom).encode()) == contenu
    print("relus et déchiffrés à l'identique")

    recu = bytearray(c.get("/blobs/etat.json").content)
    recu[20] ^= 0x01
    try:
        AESGCM(cle).decrypt(bytes(recu[:12]), bytes(recu[12:]), (id + "etat.json").encode())
        raise SystemExit("un blob altéré a été accepté")
    except InvalidTag:
        print("blob altéré d'un octet : refusé")

    r = c.put("/blobs/prevu.json", content=b"x", headers={"Content-Type": "application/octet-stream"})
    print("prevu.json sans abonnement :", r.status_code, "(402 attendu, 200 si RELAY_GRATUIT=1)")

    assert c.delete("/comptes/moi").status_code == 204
    assert c.get("/blobs").status_code == 401
    print("compte supprimé, jeton refusé ensuite")
    print("valeur en clair à chercher sur le serveur : 95.7")


if __name__ == "__main__":
    main()
