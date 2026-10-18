def test_sante_repond_ok(client):
    r = client.get("/sante")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_schema_cree(base_tmp):
    tables = {r[0] for r in base_tmp.execute("select name from sqlite_master where type='table'")}
    assert {"comptes", "blobs", "reveils"} <= tables


def test_hote_d_ecoute_depuis_env(monkeypatch):
    from relay_serveur.config import Config
    monkeypatch.setenv("RELAY_HOTE", "0.0.0.0")
    assert Config.depuis_env().hote == "0.0.0.0"
    monkeypatch.delenv("RELAY_HOTE")
    assert Config.depuis_env().hote == "127.0.0.1"
