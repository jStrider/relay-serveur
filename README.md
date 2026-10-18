# relay-serveur

Relais chiffré de bout en bout entre l'app Relay (iPhone) et un agent IA : il stocke des blobs qu'il ne peut pas lire, réveille l'iPhone à la demande et fait respecter l'abonnement. Design : dépôt `relay`, `docs/superpowers/specs/2026-10-18-relay-v2-design.md`.

```sh
uv sync              # dépendances
uv run pytest -q     # tests
uv run relay-serveur # lance sur 127.0.0.1:8780 (variables RELAY_* et APNS_* dans l'environnement)
```

## Déploiement

`.env` à la racine (voir `.env.example`), la clé SSH `~/.ssh/hermes_ed25519`, `terraform`, `ansible`, `uv`.

| Commande | Effet |
|---|---|
| `make test` | Lance les tests |
| `make infra` | Crée ou met à jour le VPS, `relay.<zone>` et le bucket de sauvegarde |
| `make deploy` | Construit la wheel et déploie l'application, Caddy et les sauvegardes |
| `make ssh` | Shell sur le VPS |
| `make backup-now` / `make backup-status` | Sauvegarde immédiate / liste des snapshots |
| `make restore` | Remet la base depuis le dernier snapshot |

Le serveur ne lit jamais les blobs : voir `vecteurs/LISEZMOI.md` pour le contrat de chiffrement entre l'app et le client.
