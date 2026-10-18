"""Lance le relais sur la boucle locale ; Caddy termine TLS devant. Une tâche de fond purge les comptes
inactifs depuis 365 jours et écrit les compteurs du jour, une fois par heure."""

import logging
import threading
import time

import uvicorn

from . import base, comptes, limites
from .app import creer_app
from .config import Config


def entretien(connexion, config):
    while True:
        try:
            comptes.purger_inactifs(connexion, time.time() - 365 * 86400)
            limites.ecrire_compteurs(connexion, config.compteurs, time.time())
        except Exception:
            logging.getLogger("relay").exception("entretien")
        time.sleep(3600)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    config = Config.depuis_env()
    connexion = base.ouvrir(config.base)
    threading.Thread(target=entretien, args=(connexion, config), daemon=True).start()
    uvicorn.run(creer_app(config, connexion), host=config.hote, port=8780, log_level="warning")


if __name__ == "__main__":
    main()
