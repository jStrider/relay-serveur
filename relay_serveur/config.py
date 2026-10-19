"""Configuration lue dans l'environnement ; aucune valeur secrète par défaut."""

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    base: str = "/var/lib/relay/relay.db"
    gratuit: bool = False  # RELAY_GRATUIT=1 : aucune barrière d'abonnement (auto-hébergement)
    apns_cle: str = ""  # chemin du .p8
    apns_cle_id: str = ""
    apns_equipe: str = ""
    apns_bundle: str = ""
    apple_app_id: int = 0
    apple_env: str = "Sandbox"  # Sandbox ou Production
    apple_racines: str = ""  # dossier des certificats racine Apple
    compteurs: str = ""  # fichier des compteurs d'usage par jour
    hote: str = "127.0.0.1"  # RELAY_HOTE=0.0.0.0 pour un essai depuis un iPhone sur le réseau local, jamais en production (Caddy devant)
    max_blobs: int = 1000
    max_octets: int = 200 * 1024 * 1024
    max_blob: int = 1024 * 1024
    requetes_par_minute: int = 600  # la première synchro dépose 13 mois × 14 métriques + les séances en une rafale
    reveils_par_heure: int = 6
    creations_par_heure_ip: int = 10
    extra: dict = field(default_factory=dict)

    @classmethod
    def depuis_env(cls) -> "Config":
        e = os.environ
        return cls(
            base=e.get("RELAY_BASE", cls.base),
            gratuit=e.get("RELAY_GRATUIT", "0") == "1",
            apns_cle=e.get("APNS_CLE", ""),
            apns_cle_id=e.get("APNS_CLE_ID", ""),
            apns_equipe=e.get("APNS_EQUIPE", ""),
            apns_bundle=e.get("APNS_BUNDLE", ""),
            apple_app_id=int(e.get("APPLE_APP_ID", "0") or 0),
            apple_env=e.get("APPLE_ENV", "Sandbox"),
            apple_racines=e.get("APPLE_RACINES", ""),
            compteurs=e.get("RELAY_COMPTEURS", ""),
            hote=e.get("RELAY_HOTE") or "127.0.0.1",
        )
