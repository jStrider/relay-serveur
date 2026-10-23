# Vecteurs de chiffrement

Contrat entre l'app Relay (CryptoKit) et le client `relay-agent` (`cryptography`). Le serveur ne chiffre rien : il publie ce contrat.

Un blob déposé sur le relais vaut `nonce (12 octets) || AES-256-GCM(cle, nonce, clair, aad)` avec `aad = id_du_compte || nom_du_blob` (chaîne UTF-8, sans séparateur). Le tag GCM de 16 octets suit le chiffré, comme le produisent CryptoKit (`AES.GCM.seal(...).combined` sans le nonce) et `cryptography` (`AESGCM.encrypt`). L'`aad` lie chaque blob à son nom : déplacé ou renommé, il ne se déchiffre plus.

`chiffrement.json` : un tableau de cas, valeurs en hexadécimal. `cle` (32 octets), `nonce` (12), `clair`, `chiffre` (sortie d'AES-GCM, tag compris), `blob_chiffre` (`nonce || chiffre`, ce qui transite). Trois cas : clair vide, JSON court, 100 ko. Un nom de blob hors contrat (`^metriques/[a-z_]+/AAAA-MM\.json$`, `^seances/AAAA-MM-JJ-[A-Za-z0-9-]+\.json$`, `etat.json`, `prevu.json`) n'a pas de vecteur : le relais le refuse avant tout chiffrement.

Les valeurs ont été tirées au sort une fois par `outils/generer_vecteurs.py` puis figées ; ne pas les régénérer.

## Appairage par code court (`appairage.json`)

Contrat entre `relay-agent` (`cryptography`) et l'app (CryptoKit) pour relier un agent sans manipuler de secret. L'agent ouvre la session avec un engagement, `engagement = SHA-256(clé publique de l'agent, 32 octets bruts)`, et ne révèle sa clé qu'après avoir lu celle de l'app ; l'app vérifie que le SHA-256 de la clé révélée vaut l'engagement avant d'afficher le code. Sans cet engagement, un relais malveillant qui verrait la clé de l'agent avant de choisir la clé qu'il lui présente pourrait chercher par force brute (10⁶ essais) deux échanges qui donnent le même code. `secret = X25519(privée, publique de l'autre)` ; `cle = HKDF-SHA256(secret, sel = session UTF-8, info = "relay-appairage-cle", 32 octets)` ; `code = int(HKDF-SHA256(secret, sel = session, info = "relay-appairage-code", 4 octets), big-endian) mod 1 000 000`, sur six chiffres ; `identite_chiffree = nonce(12) || AES-256-GCM(cle, nonce, phrase UTF-8, aad = session)`. Le vecteur donne les deux clés privées, les clés publiques, l'engagement, la clé dérivée, le code, le nonce et le chiffré, en hexadécimal (sur le relais, l'engagement et les clés transitent en base64url sans remplissage) ; généré une fois par `outils/generer_vecteurs_appairage.py` puis figé.
