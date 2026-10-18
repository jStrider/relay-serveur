# relay-serveur : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un relais HTTP qui stocke des blobs chiffrés par compte sans jamais pouvoir les lire, réveille l'iPhone à la demande, fait respecter l'abonnement, et se déploie sur un petit VPS OVH par `make infra` et `make deploy`.

**Architecture:** Une app FastAPI, un fichier SQLite, un module par responsabilité (comptes, blobs, APNs, rafraîchissement, abonnement, limites). Le serveur ne connaît aucune clé de chiffrement : il ne manipule que des octets opaques, des horodatages et des identifiants. Le déploiement reprend la mécanique d'OVH-perso (Terraform pour le VPS, le DNS et le bucket ; Ansible pour la machine ; restic pour les sauvegardes).

**Tech Stack:** Python 3.13, FastAPI, uvicorn, stdlib `sqlite3` (WAL), `httpx[http2]` pour APNs, `PyJWT[crypto]`, `app-store-server-library` (bibliothèque officielle Apple) pour vérifier les transactions, `pytest` via `uv`. Terraform (provider `ovh`), Ansible, Caddy, restic, fail2ban.

**Spec:** `/Users/julienrenaudperso/Documents/git/perso/relay/docs/superpowers/specs/2026-10-18-relay-v2-design.md` (sections 1, 2, 5 et « Vérification »). Le modèle de référence du rafraîchissement est le récepteur v1 : `/Users/julienrenaudperso/Documents/git/perso/OVH-perso/ansible/files/hermes-sante.py` (fonctions `rafraichir`, `_reveiller`, `envoyer_notification`) et ses tests.

## Global Constraints

- Français partout : identifiants, messages, commentaires, documents. YAGNI.
- Aucun corps de requête ni contenu de blob dans un journal, une exception ou une réponse d'erreur : les journaux portent méthode, chemin, code, identifiant de compte, durée.
- Toute route sauf `GET /sante` et `POST /comptes` exige `Authorization: Bearer <jeton>` ; le serveur compare `SHA-256(jeton)` en temps constant et ne stocke jamais le jeton.
- Noms de blobs autorisés, et rien d'autre : `metriques/<nom>/<AAAA-MM>.json` (`nom` en `[a-z_]+`), `seances/<AAAA-MM-JJ>-<id>.json` (`id` en `[A-Za-z0-9-]+`), `etat.json`, `prevu.json`. Tout autre nom → `400`.
- Limites : blob 1 Mo (`413`), 1 000 blobs et 200 Mo par compte (`507`), 120 requêtes par minute et par compte (`429`), 6 réveils par heure (`429`), `POST /comptes` 10 par heure et par adresse IP (`429`).
- Rafraîchissement : grâce 120 s sur l'horodatage de dépôt du dernier `etat.json`, attente 25 s, un seul réveil à la fois par compte, codes `200/402/429/502/503/504` comme en v1.
- `RELAY_GRATUIT=1` désactive toute barrière d'abonnement (auto-hébergement). Sinon `PUT /blobs/prevu.json` et `POST /rafraichir` répondent `402` sans abonnement valide.
- Variables d'environnement (fichier `/etc/relay/relay.env` en production) : `RELAY_BASE` (chemin SQLite), `RELAY_GRATUIT`, `APNS_CLE`, `APNS_CLE_ID`, `APNS_EQUIPE`, `APNS_BUNDLE`, `APPLE_APP_ID`, `APPLE_ENV` (`Sandbox`/`Production`), `APPLE_RACINES` (dossier des certificats racine Apple). Pas de valeur secrète par défaut.
- Tests : `uv run pytest` vert avant chaque commit ; les tests n'appellent jamais Apple (faux envoyeur APNs, faux vérificateur de transaction injectés).
- Python 3.13 sur le VPS (Debian 13) ; le service tourne sous l'utilisateur `relay`, unité systemd durcie, venv dans `/opt/relay`.

## Review Focus

- Nom de blob avec `..`, `/` initial, caractère hors liste ou encodage URL malin : `400`, rien d'écrit (test en tâche 3).
- Le jeton du compte A ne lit ni n'écrit les blobs du compte B, même avec un nom identique (test en tâche 3).
- Compte supprimé : ses blobs disparaissent et son jeton répond `401` ensuite (test en tâche 2).
- Rafraîchissement d'un compte sans appareil enregistré, ou dont APNs répond `410` : `503` ou `502`, appareil oublié, jamais une exception (test en tâche 5).
- Transaction StoreKit invalide, expirée ou d'un autre bundle : `400`, l'abonnement reste inchangé (test en tâche 6).

---

### Task 1: Squelette, configuration, base SQLite et `GET /sante`

**Files:**
- Create: `pyproject.toml` (paquet `relay_serveur`, dépendances ci-dessus, `[project.scripts] relay-serveur = "relay_serveur.__main__:main"`), `relay_serveur/__init__.py`, `relay_serveur/config.py`, `relay_serveur/base.py`, `relay_serveur/app.py`, `relay_serveur/__main__.py`, `tests/conftest.py`, `tests/test_sante.py`, `.gitignore`, `README.md` (dix lignes : rôle, `uv run pytest`, `uv run relay-serveur`)

**Interfaces:**
- Produces: `config.Config` (dataclass lue depuis l'environnement, `Config.depuis_env()`), `base.ouvrir(chemin) -> sqlite3.Connection` (WAL, `foreign_keys=ON`, schéma créé si absent : `comptes(id TEXT PRIMARY KEY, jeton_hache BLOB, apns TEXT, apns_env TEXT, cree_le REAL, vu_le REAL, abonne_jusqu_au REAL)`, `blobs(compte TEXT, nom TEXT, contenu BLOB, taille INTEGER, maj REAL, PRIMARY KEY(compte, nom))`, `reveils(compte TEXT, quand REAL)`), `app.creer_app(config, base, envoyeur=None, verificateur=None) -> FastAPI` (les deux derniers injectables pour les tests), `conftest.client` (TestClient sur une base temporaire).

- [ ] **Step 1: Tests**

```python
def test_sante_repond_ok(client):
    r = client.get("/sante")
    assert r.status_code == 200 and r.json() == {"status": "ok"}

def test_schema_cree(base_tmp):
    tables = {r[0] for r in base_tmp.execute("select name from sqlite_master where type='table'")}
    assert {"comptes", "blobs", "reveils"} <= tables
```

- [ ] **Step 2: Vérifier l'échec** — Run: `uv run pytest -q`. Expected: ImportError.
- [ ] **Step 3: Implémenter** `config.py`, `base.py`, `app.py` (route `/sante`), `__main__.py` (`uvicorn.run(host=127.0.0.1, port=8780)`).
- [ ] **Step 4: Vérifier le succès** — Run: `uv run pytest -q`. Expected: 2 passed.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "Squelette FastAPI, configuration, base SQLite, GET /sante"`

### Task 2: Comptes et authentification

**Files:**
- Create: `relay_serveur/comptes.py`, `tests/test_comptes.py`
- Modify: `relay_serveur/app.py`

**Interfaces:**
- Produces: `comptes.creer(base, id, jeton) -> bool`, `comptes.authentifier(base, entete) -> str | None` (identifiant si le jeton correspond, met `vu_le` à jour), dépendance FastAPI `compte_courant` qui renvoie l'id ou lève `401`, `comptes.supprimer(base, id)`, `comptes.purger_inactifs(base, avant: float) -> int`. Routes `POST /comptes` (`{"id","jeton"}` → `201`, `409` si l'id existe, `400` si formats faux : id base32 de 26 caractères, jeton base64url de 43 caractères), `DELETE /comptes/moi` → `204`.

- [ ] **Step 1: Tests** : `test_creation_puis_authentification`, `test_id_existant_409`, `test_jeton_faux_401`, `test_sans_entete_401`, `test_suppression_puis_401` (et plus aucun blob : écrire un blob avant via `base` direct), `test_purge_inactifs_12_mois` (un compte avec `vu_le` vieux de 400 jours est purgé, un récent non), `test_creation_limitee_par_ip` (11ᵉ création depuis la même IP → `429`).
- [ ] **Step 2: Vérifier l'échec**, **Step 3: Implémenter** (limite IP : dictionnaire en mémoire `{ip: deque}`), **Step 4: Vérifier le succès**, **Step 5: Commit** — `git commit -am "Comptes : création, authentification par jeton haché, suppression, purge"`

### Task 3: Blobs

**Files:**
- Create: `relay_serveur/blobs.py`, `tests/test_blobs.py`
- Modify: `relay_serveur/app.py`

**Interfaces:**
- Produces: `blobs.nom_valide(nom) -> bool` (expression régulière des contraintes globales), `blobs.deposer(base, compte, nom, contenu) -> float` (horodatage), `blobs.lister(base, compte, depuis=None) -> list[dict]`, `blobs.lire(base, compte, nom) -> bytes | None`, `blobs.retirer(base, compte, nom) -> bool`, `blobs.usage(base, compte) -> (nombre, octets)`. Routes `PUT /blobs/{nom:path}` (corps `application/octet-stream`, → `{"maj": …}`), `GET /blobs?depuis=`, `GET /blobs/{nom:path}` (octets, `404`), `DELETE /blobs/{nom:path}` (`204`/`404`).

- [ ] **Step 1: Tests** : `test_depot_puis_lecture_octets_identiques`, `test_liste_avec_depuis`, `test_nom_refuse` (paramétré : `../x`, `/etat.json`, `metriques/Pas/2026-10.json`, `seances/x.json`, `etat.json/`, `%2e%2e/etat.json`), `test_isolation_entre_comptes`, `test_blob_trop_gros_413` (1 Mo + 1 octet, rien d'écrit), `test_quota_nombre_507` (limite abaissée par la config de test à 3 blobs), `test_quota_octets_507`, `test_prevu_reserve_aux_abonnes_402` (avec `RELAY_GRATUIT=0` et compte non abonné ; `200` avec `RELAY_GRATUIT=1`), `test_retrait_404_si_absent`.
- [ ] **Step 2: Vérifier l'échec**, **Step 3: Implémenter**, **Step 4: Vérifier le succès**, **Step 5: Commit** — `git commit -am "Blobs : dépôt, liste, lecture, retrait, quotas, isolation"`

### Task 4: Vecteurs de chiffrement partagés

Le serveur ne chiffre rien, mais il est le dépôt ouvert du contrat entre l'app (CryptoKit) et le client (`cryptography`). Les vecteurs fixent ce contrat et les deux autres plans les rejouent.

**Files:**
- Create: `vecteurs/chiffrement.json`, `vecteurs/LISEZMOI.md` (le format : `nonce(12) || AES-256-GCM(cle, nonce, clair, aad = id || nom)`, encodages hexadécimaux), `tests/test_vecteurs.py`, `outils/generer_vecteurs.py`

**Interfaces:**
- Produces: un fichier JSON `[{"nom": "…", "cle": hex, "id": "…", "blob": "metriques/step_count/2026-10.json", "nonce": hex, "clair": hex, "chiffre": hex}]` avec quatre cas : contenu vide, contenu JSON court, contenu de 100 ko, nom de blob accentué refusé (pas de vecteur : le nom est invalide). Les valeurs sont générées une fois par `outils/generer_vecteurs.py` avec des clés tirées au sort puis figées dans le dépôt.

- [ ] **Step 1: Test** : `test_vecteurs_rejoues` (pour chaque vecteur, `AESGCM(cle).encrypt(nonce, clair, aad)` == `chiffre` et le déchiffrement inverse redonne `clair`) et `test_aad_lie_le_nom` (le même blob avec un autre nom ne se déchiffre pas : `InvalidTag`).
- [ ] **Step 2: Vérifier l'échec** (fichier absent), **Step 3: Générer** les vecteurs et écrire le LISEZMOI, **Step 4: Vérifier le succès**, **Step 5: Commit** — `git commit -am "Vecteurs de chiffrement AES-256-GCM partagés avec l'app et le client"`

### Task 5: Appareil, APNs et rafraîchissement

**Files:**
- Create: `relay_serveur/apns.py`, `relay_serveur/rafraichir.py`, `tests/test_rafraichir.py`
- Modify: `relay_serveur/app.py`

**Interfaces:**
- Produces: `apns.Envoyeur(config)` avec `envoyer(token, env) -> int` (JWT ES256 en cache 50 min, `httpx.Client(http2=True)` vers `api.push.apple.com` ou `api.sandbox.push.apple.com` selon `env`, en-têtes `apns-topic`, `apns-push-type: background`, `apns-priority: 5`, `apns-expiration: 0`, corps `{"aps": {"content-available": 1}}` ; `0` si l'envoi échoue), `rafraichir.Rafraichisseur(base, envoyeur, attente=25.0)` avec `rafraichir(compte, maintenant) -> (code, dict)` portant la logique v1 : grâce sur `maj` du blob `etat.json`, verrou par compte, budget 6/h dans `reveils`, `503` sans appareil, `410` → appareil effacé et `502`, sondage du nouvel `etat.json` toutes les 0,5 s, `500` interne qui ne bloque jamais les suivants. Routes `POST /appareil` (`{"token", "env": "sandbox"|"production"}`), `POST /rafraichir` (`402` sans abonnement sauf `RELAY_GRATUIT`).

- [ ] **Step 1: Tests** (faux envoyeur injecté qui enregistre les appels ; un `threading.Timer` dépose `etat.json` 0,3 s après) : `test_synchro_recente_sans_reveil`, `test_sans_appareil_503`, `test_reveil_puis_etat_200`, `test_pas_de_reponse_504`, `test_apns_410_oublie_l_appareil_502`, `test_budget_6_par_heure_429`, `test_deux_appels_simultanes_un_seul_reveil`, `test_exception_ne_bloque_pas_les_suivants`, `test_non_abonne_402`, `test_env_sandbox_transmis_a_l_envoyeur`.
- [ ] **Step 2: Vérifier l'échec**, **Step 3: Implémenter** (porter depuis `hermes-sante.py`, en remplaçant `curl` par `httpx`), **Step 4: Vérifier le succès** (`uv run pytest -q`, moins de 15 s), **Step 5: Commit** — `git commit -am "Appareil, notifications silencieuses APNs, rafraîchissement à la demande"`

### Task 6: Abonnement App Store

**Files:**
- Create: `relay_serveur/abonnement.py`, `tests/test_abonnement.py`, `deploy/apple/` (certificats racine Apple `AppleRootCA-G3.cer`, `AppleRootCA-G2.cer`, `AppleIncRootCertificate.cer`, `AppleComputerRootCertificate.cer`, téléchargés depuis apple.com/certificateauthority, avec leur empreinte notée dans un `LISEZMOI.md`)
- Modify: `relay_serveur/app.py`, `relay_serveur/blobs.py` (dépendance `abonne_requis`)

**Interfaces:**
- Produces: `abonnement.Verificateur` (protocole : `expire_le(jws: str) -> float`, lève `ValueError` si la signature, le bundle ou l'app ne correspondent pas), `abonnement.VerificateurApple(config)` construit sur `SignedDataVerifier` de `app-store-server-library` avec `enable_online_checks=False`, `abonnement.est_abonne(base, compte, maintenant) -> bool` (`True` si `RELAY_GRATUIT` ou `abonne_jusqu_au > maintenant`), dépendance FastAPI `abonne_requis` → `402 {"status": "abonnement requis"}`. Route `POST /abonnement` (`{"transaction": jws}` → `200 {"abonne_jusqu_au": …}`, `400` si invalide).

- [ ] **Step 1: Tests** (faux vérificateur injecté) : `test_transaction_valide_met_a_jour`, `test_transaction_invalide_400_et_inchange`, `test_abonnement_expire_402_sur_prevu`, `test_gratuit_ignore_l_abonnement`, et un test réel du câblage : `test_verificateur_apple_rejette_un_jws_bidon` (`VerificateurApple` avec les vrais certificats racine lève `ValueError` sur `"a.b.c"`).
- [ ] **Step 2: Vérifier l'échec**, **Step 3: Implémenter**, **Step 4: Vérifier le succès**, **Step 5: Commit** — `git commit -am "Abonnement : vérification des transactions App Store, barrière 402, mode gratuit"`

### Task 7: Limites de débit, journalisation, purge périodique

**Files:**
- Create: `relay_serveur/limites.py`, `tests/test_limites.py`
- Modify: `relay_serveur/app.py`, `relay_serveur/__main__.py`

**Interfaces:**
- Produces: middleware `Debit` (120 requêtes par minute et par compte authentifié, `429` au-delà, compteurs en mémoire), middleware `Journal` (une ligne par requête : horodatage, méthode, chemin sans paramètres, code, compte ou `-`, durée en ms ; jamais le corps, jamais l'entête d'autorisation), tâche de fond au démarrage qui appelle `comptes.purger_inactifs` une fois par jour (365 jours) et écrit dans `RELAY_COMPTEURS` (fichier texte, une ligne par jour : date, comptes actifs, dépôts d'`etat.json`) le seul indicateur d'usage, sans identifiant, gestionnaire d'exception global qui répond `500 {"status": "erreur interne"}` sans détail.

- [ ] **Step 1: Tests** : `test_121e_requete_429`, `test_journal_sans_corps_ni_jeton` (capture des logs : la ligne contient le code et le chemin, pas le jeton ni le contenu), `test_exception_interne_500_sans_detail`, `test_compteurs_du_jour` (après deux dépôts d'`etat.json` par deux comptes, la ligne du jour dit `2 2`).
- [ ] **Step 2-5** : échec, implémentation, succès, commit — `git commit -am "Débit, journal sans données, purge quotidienne"`

### Task 8: Déploiement : Terraform, Ansible, sauvegardes, Makefile

**Files:**
- Create: `deploy/terraform/{versions,variables,main,outputs}.tf` (repris d'OVH-perso : `ovh_vps` « relay » plan `vps-2027-model1`, datacenter France si disponible sinon UK comme Hermes, `ovh_domain_zone_record` `relay` CNAME dans `var.zone`, bucket `relay-backups-<id>` + utilisateur S3 + politique), `deploy/ansible/{site.yml,restore.yml,inventory.ini.example}`, `deploy/ansible/templates/{relay.service.j2,relay.env.j2,Caddyfile.j2,relay-backup.service.j2,relay-backup.timer.j2,relay-backup.sh.j2,restic.env.j2}`, `Makefile` (`infra`, `deploy`, `ssh`, `backup-now`, `backup-status`, `restore`, `test`), `.env.example`
- Modify: `README.md` (variables `.env`, commandes, restauration)

**Interfaces:**
- Consumes: `.env` : `OVH_*`, `RESTIC_PASSWORD`, `RELAY_ZONE` (domaine acheté par Julien), `APNS_CLE_FICHIER`, `APNS_CLE_ID`, `APNS_EQUIPE`, `APNS_BUNDLE`, `APPLE_APP_ID`, `APPLE_ENV`, `RELAY_GRATUIT`.
- Produces: sur le VPS, paquets `python3-venv caddy restic fail2ban unattended-upgrades`, utilisateur `relay`, `/opt/relay/venv` installé depuis la wheel construite en local (`uv build` dans le Makefile, copiée par Ansible), `/var/lib/relay/relay.db` (0700 relay), `/etc/relay/relay.env` (0600 root, `EnvironmentFile`), `/etc/relay/apns.p8` (root:relay 0640), `/etc/relay/apple/` (racines), unité `relay.service` (`User=relay`, `ProtectSystem=strict`, `ProtectHome=true`, `ReadWritePaths=/var/lib/relay`, `PrivateTmp`, `NoNewPrivileges`, `Restart=always`), Caddy `relay.<zone>` → `127.0.0.1:8780` avec le site statique plus tard, timer de sauvegarde (`sqlite3 /var/lib/relay/relay.db ".backup /var/lib/relay/relay.sauvegarde.db"` puis `restic backup`), SSH par clé seulement.

- [ ] **Step 1: Écrire** Terraform, Ansible, Makefile, `.env.example`, README.
- [ ] **Step 2: Vérifier la syntaxe** — Run: `terraform -chdir=deploy/terraform validate` et `ansible-playbook deploy/ansible/site.yml --syntax-check -i deploy/ansible/inventory.ini.example`. Expected: `Success!` et `playbook: site.yml`.
- [ ] **Step 3: Créer le VPS** (une fois le domaine connu et `.env` rempli) — Run: `make infra`. Expected: VPS créé, `relay.<zone>` résout.
- [ ] **Step 4: Déployer** — Run: `make deploy` deux fois. Expected: `failed=0`, puis `changed=0` ; `curl https://relay.<zone>/sante` → `{"status":"ok"}`.
- [ ] **Step 5: Restauration** — Run: `make backup-now`, puis `make restore` sur le même VPS (ou un VPS neuf). Expected: `GET /blobs` d'un compte de test renvoie les blobs d'avant.
- [ ] **Step 6: Commit** — `git add -A && git commit -m "Déploiement : Terraform OVH, Ansible, sauvegardes restic, Makefile"`

### Task 9: Vérification de bout en bout du serveur seul

- [ ] **Step 1:** `uv run pytest -q` vert.
- [ ] **Step 2:** Depuis le Mac, un script `outils/essai.py` : crée un compte sur `https://relay.<zone>`, dépose deux blobs chiffrés avec `cryptography` à partir d'un vecteur, les relit et les déchiffre, altère un octet et constate `InvalidTag`, tente `PUT prevu.json` → `402`, supprime le compte → `401` ensuite.
- [ ] **Step 3:** Sur le VPS, `sqlite3 /var/lib/relay/relay.db "select nom, taille from blobs"` ne montre que des noms et des tailles ; `grep -r "<valeur du clair>" /var/log /var/lib/relay` ne trouve rien.
- [ ] **Step 4:** Commit du script d'essai — `git commit -am "Script d'essai de bout en bout contre le relais déployé"`
