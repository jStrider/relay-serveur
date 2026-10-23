import base64
import hashlib
import os
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from relay_serveur import appairages
from relay_serveur import base as base_module
from relay_serveur.app import creer_app

CLE_A = base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("=")
CLE_B = base64.urlsafe_b64encode(bytes(range(32, 64))).decode().rstrip("=")


def engagement(cle):
    return base64.urlsafe_b64encode(hashlib.sha256(base64.urlsafe_b64decode(cle + "=")).digest()).decode().rstrip("=")


def ouvrir(client, cle=CLE_A):
    r = client.post("/appairages", json={"engagement": engagement(cle)})
    assert r.status_code == 201, r.text
    return r.json()["session"]


def test_creation_puis_lecture(client):
    s = ouvrir(client)
    assert len(s) == 8 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in s)
    r = client.get(f"/appairages/{s}")
    assert r.status_code == 200
    assert r.json() == {"engagement": engagement(CLE_A), "cle_publique_agent": None, "cle_publique_app": None, "identite_chiffree": None}


def test_cle_agent_apres_celle_de_l_app(client):
    s = ouvrir(client)
    assert client.put(f"/appairages/{s}/agent", json={"cle_publique_agent": CLE_A}).status_code == 409  # l'app d'abord
    client.put(f"/appairages/{s}/app", json={"cle_publique_app": CLE_B})
    assert client.put(f"/appairages/{s}/agent", json={"cle_publique_agent": CLE_A}).status_code == 200
    assert client.get(f"/appairages/{s}").json()["cle_publique_agent"] == CLE_A
    assert client.put(f"/appairages/{s}/agent", json={"cle_publique_agent": CLE_A}).status_code == 409  # une seule fois


def test_cle_agent_doit_tenir_l_engagement(client):
    s = ouvrir(client)
    client.put(f"/appairages/{s}/app", json={"cle_publique_app": CLE_B})
    assert client.put(f"/appairages/{s}/agent", json={"cle_publique_agent": CLE_B}).status_code == 400
    assert client.put(f"/appairages/{s}/agent", json={"cle_publique_agent": "court"}).status_code == 400
    assert client.get(f"/appairages/{s}").json()["cle_publique_agent"] is None


def test_ancien_schema_remplace(tmp_path):
    chemin = str(tmp_path / "ancienne.db")
    ancienne = sqlite3.connect(chemin)
    ancienne.execute("create table appairages (session text primary key, cle_agent text not null, cle_app text, identite text, cree_le real not null)")
    ancienne.execute("insert into appairages values ('ABCDEFGH', 'x', null, null, 0)")
    ancienne.commit()
    ancienne.close()
    base = base_module.ouvrir(chemin)
    colonnes = {c[1] for c in base.execute("pragma table_info(appairages)")}
    assert "engagement" in colonnes
    assert base.execute("select count(*) from appairages").fetchone()[0] == 0


def test_session_normalisee_minuscules_et_tiret(client):
    s = ouvrir(client)
    saisie = f"{s[:4].lower()}-{s[4:].lower()}"
    assert client.get(f"/appairages/{saisie}").status_code == 200
    assert appairages.normaliser(saisie) == s
    assert appairages.normaliser("abc") is None and appairages.normaliser("ABCD-EFG1") is None  # 1 hors base32


def test_inconnue_404(client):
    assert client.get("/appairages/ABCDEFGH").status_code == 404
    assert client.put("/appairages/ABCDEFGH/app", json={"cle_publique_app": CLE_B}).status_code == 404
    assert client.put("/appairages/ABCDEFGH/agent", json={"cle_publique_agent": CLE_A}).status_code == 404
    assert client.put("/appairages/ABCDEFGH/identite", json={"identite_chiffree": "AA"}).status_code == 404
    assert client.delete("/appairages/ABCDEFGH").status_code == 404


def test_expiree_404(client, base_tmp):
    s = ouvrir(client)
    base_tmp.execute("update appairages set cree_le = ? where session = ?", (time.time() - 11 * 60, s))
    assert client.get(f"/appairages/{s}").status_code == 404
    assert appairages.purger(base_tmp, time.time() - 600) == 1


def test_cle_app_une_seule_fois_409(client):
    s = ouvrir(client)
    assert client.put(f"/appairages/{s}/app", json={"cle_publique_app": CLE_B}).status_code == 200
    assert client.put(f"/appairages/{s}/app", json={"cle_publique_app": CLE_A}).status_code == 409
    assert client.get(f"/appairages/{s}").json()["cle_publique_app"] == CLE_B


def test_identite_puis_suppression(client):
    s = ouvrir(client)
    client.put(f"/appairages/{s}/app", json={"cle_publique_app": CLE_B})
    assert client.put(f"/appairages/{s}/identite", json={"identite_chiffree": "QUJD"}).status_code == 200
    assert client.get(f"/appairages/{s}").json()["identite_chiffree"] == "QUJD"
    assert client.delete(f"/appairages/{s}").status_code == 204
    assert client.get(f"/appairages/{s}").status_code == 404


def test_corps_trop_gros_413(client):
    s = ouvrir(client)
    r = client.put(f"/appairages/{s}/identite", json={"identite_chiffree": "A" * 5000})
    assert r.status_code == 413


def test_engagement_mal_forme_400(client):
    assert client.post("/appairages", json={"engagement": "court"}).status_code == 400
    assert client.post("/appairages", json={"engagement": engagement(CLE_A) + "AA"}).status_code == 400
    assert client.post("/appairages", json={"cle_publique_agent": CLE_A}).status_code == 400  # ancien contrat
    assert client.post("/appairages", json={}).status_code == 400


def test_creation_limitee_par_ip(client):
    for _ in range(10):
        ouvrir(client)
    assert client.post("/appairages", json={"engagement": engagement(CLE_A)}).status_code == 429


def test_nouvelle_session_aleatoire():
    assert appairages.nouvelle_session() != appairages.nouvelle_session()
