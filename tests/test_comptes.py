import time

from relay_serveur import comptes

ID = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"  # 26 caractères base32
JETON = "a" * 43  # 43 caractères base64url


def creer(client, id=ID, jeton=JETON):
    return client.post("/comptes", json={"id": id, "jeton": jeton})


def entete(jeton=JETON):
    return {"Authorization": f"Bearer {jeton}"}


def test_creation_puis_authentification(client, base_tmp):
    assert creer(client).status_code == 201
    assert comptes.authentifier(base_tmp, f"Bearer {JETON}") == ID
    assert base_tmp.execute("select jeton_hache from comptes").fetchone()[0] != JETON.encode()


def test_id_existant_409(client):
    creer(client)
    assert creer(client, jeton="b" * 43).status_code == 409


def test_formats_faux_400(client):
    assert creer(client, id="court").status_code == 400
    assert creer(client, jeton="court").status_code == 400


def test_jeton_faux_401(client):
    creer(client)
    assert client.delete("/comptes/moi", headers=entete("b" * 43)).status_code == 401


def test_sans_entete_401(client):
    creer(client)
    assert client.delete("/comptes/moi").status_code == 401


def test_suppression_puis_401(client, base_tmp):
    creer(client)
    base_tmp.execute("insert into blobs values (?, 'etat.json', x'00', 1, ?)", (ID, time.time()))
    assert client.delete("/comptes/moi", headers=entete()).status_code == 204
    assert base_tmp.execute("select count(*) from blobs where compte = ?", (ID,)).fetchone()[0] == 0
    assert client.delete("/comptes/moi", headers=entete()).status_code == 401


def test_purge_inactifs_12_mois(client, base_tmp):
    creer(client)
    creer(client, id="B" * 26, jeton="b" * 43)
    base_tmp.execute("update comptes set vu_le = ? where id = ?", (time.time() - 400 * 86400, ID))
    assert comptes.purger_inactifs(base_tmp, avant=time.time() - 365 * 86400) == 1
    assert [r[0] for r in base_tmp.execute("select id from comptes")] == ["B" * 26]


def test_creation_limitee_par_ip(client):
    for i in range(10):
        assert creer(client, id=chr(65 + i) * 26, jeton=chr(97 + i) * 43).status_code == 201
    assert creer(client, id="Z" * 26, jeton="z" * 43).status_code == 429
