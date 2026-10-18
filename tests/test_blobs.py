import time

import pytest
from fastapi.testclient import TestClient

from relay_serveur.app import creer_app
from relay_serveur import base as base_module
from tests.test_comptes import ID, JETON, creer, entete

OCTETS = {"Content-Type": "application/octet-stream"}


@pytest.fixture
def abonne(client):
    creer(client)
    return client


def deposer(client, nom, contenu=b"\x00\x01\x02", jeton=JETON):
    return client.put(f"/blobs/{nom}", content=contenu, headers={**entete(jeton), **OCTETS})


def test_depot_puis_lecture_octets_identiques(abonne):
    r = deposer(abonne, "metriques/step_count/2026-10.json", b"\x00\xff" * 10)
    assert r.status_code == 200 and "maj" in r.json()
    r = abonne.get("/blobs/metriques/step_count/2026-10.json", headers=entete())
    assert r.status_code == 200 and r.content == b"\x00\xff" * 10


def test_liste_avec_depuis(abonne):
    deposer(abonne, "etat.json")
    t = time.time() + 1
    deposer(abonne, "seances/2026-10-18-W1.json")
    tout = abonne.get("/blobs", headers=entete()).json()
    assert {b["nom"] for b in tout} == {"etat.json", "seances/2026-10-18-W1.json"}
    assert set(tout[0]) == {"nom", "taille", "maj"}
    recents = abonne.get("/blobs", params={"depuis": t}, headers=entete()).json()
    assert [b["nom"] for b in recents] == [] or all(b["maj"] >= t for b in recents)


@pytest.mark.parametrize("nom", ["../x", "/etat.json", "metriques/Pas/2026-10.json", "seances/x.json", "etat.json/", "%2e%2e/etat.json",
                                 "metriques/step_count/2026-1.json", "autre.json", "metriques/step_count/2026-10.json.bak"])
def test_nom_refuse(abonne, nom):
    r = abonne.put(f"/blobs/{nom}", content=b"x", headers={**entete(), **OCTETS})
    assert r.status_code in (400, 404), nom
    assert abonne.get("/blobs", headers=entete()).json() == []


def test_isolation_entre_comptes(abonne):
    creer(abonne, id="B" * 26, jeton="b" * 43)
    deposer(abonne, "etat.json", b"A")
    deposer(abonne, "etat.json", b"B", jeton="b" * 43)
    assert abonne.get("/blobs/etat.json", headers=entete()).content == b"A"
    assert abonne.get("/blobs/etat.json", headers=entete("b" * 43)).content == b"B"
    assert abonne.delete("/blobs/etat.json", headers=entete("b" * 43)).status_code == 204
    assert abonne.get("/blobs/etat.json", headers=entete()).content == b"A"


def test_blob_trop_gros_413(abonne, config):
    r = deposer(abonne, "etat.json", b"x" * (config.max_blob + 1))
    assert r.status_code == 413
    assert abonne.get("/blobs", headers=entete()).json() == []


def test_quota_nombre_507(config, base_tmp):
    config.max_blobs = 3
    c = TestClient(creer_app(config, base_tmp))
    creer(c)
    for mois in ("2026-07", "2026-08", "2026-09"):
        assert deposer(c, f"metriques/step_count/{mois}.json").status_code == 200
    assert deposer(c, "metriques/step_count/2026-10.json").status_code == 507
    assert deposer(c, "metriques/step_count/2026-09.json", b"maj").status_code == 200  # remplacer ne compte pas


def test_quota_octets_507(config, base_tmp):
    config.max_octets = 10
    c = TestClient(creer_app(config, base_tmp))
    creer(c)
    assert deposer(c, "etat.json", b"x" * 8).status_code == 200
    assert deposer(c, "prevu.json", b"x" * 8).status_code in (402, 507)
    assert deposer(c, "seances/2026-10-18-W1.json", b"x" * 8).status_code == 507


def test_prevu_reserve_aux_abonnes_402(config, base_tmp):
    c = TestClient(creer_app(config, base_tmp))
    creer(c)
    assert deposer(c, "prevu.json").status_code == 402
    base_tmp.execute("update comptes set abonne_jusqu_au = ? where id = ?", (time.time() + 3600, ID))
    assert deposer(c, "prevu.json").status_code == 200
    config.gratuit = True
    base_tmp.execute("update comptes set abonne_jusqu_au = null where id = ?", (ID,))
    assert deposer(c, "prevu.json").status_code == 200


def test_retrait_404_si_absent(abonne):
    assert abonne.delete("/blobs/etat.json", headers=entete()).status_code == 404
    assert abonne.get("/blobs/etat.json", headers=entete()).status_code == 404
