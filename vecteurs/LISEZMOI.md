# Vecteurs de chiffrement

Contrat entre l'app Relay (CryptoKit) et le client `relay-agent` (`cryptography`). Le serveur ne chiffre rien : il publie ce contrat.

Un blob déposé sur le relais vaut `nonce (12 octets) || AES-256-GCM(cle, nonce, clair, aad)` avec `aad = id_du_compte || nom_du_blob` (chaîne UTF-8, sans séparateur). Le tag GCM de 16 octets suit le chiffré, comme le produisent CryptoKit (`AES.GCM.seal(...).combined` sans le nonce) et `cryptography` (`AESGCM.encrypt`). L'`aad` lie chaque blob à son nom : déplacé ou renommé, il ne se déchiffre plus.

`chiffrement.json` : un tableau de cas, valeurs en hexadécimal. `cle` (32 octets), `nonce` (12), `clair`, `chiffre` (sortie d'AES-GCM, tag compris), `blob_chiffre` (`nonce || chiffre`, ce qui transite). Trois cas : clair vide, JSON court, 100 ko. Un nom de blob hors contrat (`^metriques/[a-z_]+/AAAA-MM\.json$`, `^seances/AAAA-MM-JJ-[A-Za-z0-9-]+\.json$`, `etat.json`, `prevu.json`) n'a pas de vecteur : le relais le refuse avant tout chiffrement.

Les valeurs ont été tirées au sort une fois par `outils/generer_vecteurs.py` puis figées ; ne pas les régénérer.
