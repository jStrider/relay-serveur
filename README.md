# relay-serveur

Relais chiffré de bout en bout entre l'app Relay (iPhone) et un agent IA : il stocke des blobs qu'il ne peut pas lire, réveille l'iPhone à la demande et fait respecter l'abonnement. Design : dépôt `relay`, `docs/superpowers/specs/2026-10-18-relay-v2-design.md`.

```sh
uv sync              # dépendances
uv run pytest -q     # tests
uv run relay-serveur # lance sur 127.0.0.1:8780 (variables RELAY_* et APNS_* dans l'environnement)
```
