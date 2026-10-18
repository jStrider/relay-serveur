import logging
import time

from fastapi.testclient import TestClient

from relay_serveur import blobs
from relay_serveur.app import creer_app
from tests.test_comptes import ID, JETON, creer, entete


def test_121e_requete_429(config, base_tmp):
    config.requetes_par_minute = 5
    c = TestClient(creer_app(config, base_tmp))
    creer(c)
    codes = [c.get("/blobs", headers=entete()).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


def test_journal_sans_corps_ni_jeton(client, caplog):
    creer(client)
    with caplog.at_level(logging.INFO, logger="relay"):
        client.put("/blobs/etat.json", content=b"SECRET-CLAIR", headers={**entete(), "Content-Type": "application/octet-stream"})
    texte = "\n".join(r.getMessage() for r in caplog.records)
    assert "PUT /blobs/etat.json 200" in texte and ID in texte
    assert "SECRET-CLAIR" not in texte and JETON not in texte


def test_exception_interne_500_sans_detail(config, base_tmp):
    c = TestClient(creer_app(config, base_tmp), raise_server_exceptions=False)
    creer(c)
    base_tmp.close()  # toute requête suivante explose dans SQLite
    r = c.get("/blobs", headers=entete())
    assert r.status_code == 500 and r.json() == {"status": "erreur interne"}


def test_compteurs_du_jour(config, base_tmp, tmp_path):
    config.compteurs = str(tmp_path / "compteurs.txt")
    c = TestClient(creer_app(config, base_tmp))
    creer(c)
    creer(c, id="B" * 26, jeton="b" * 43)
    for jeton in (JETON, "b" * 43):
        c.put("/blobs/etat.json", content=b"{}", headers={**entete(jeton), "Content-Type": "application/octet-stream"})
    from relay_serveur.limites import ecrire_compteurs
    ecrire_compteurs(base_tmp, config.compteurs, time.time())
    ligne = (tmp_path / "compteurs.txt").read_text().strip().splitlines()[-1]
    assert ligne.endswith(" 2 2")
