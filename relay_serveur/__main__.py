"""Lance le relais sur la boucle locale ; Caddy termine TLS devant."""

import uvicorn

from . import base
from .app import creer_app
from .config import Config


def main():
    config = Config.depuis_env()
    uvicorn.run(creer_app(config, base.ouvrir(config.base)), host="127.0.0.1", port=8780, log_level="warning")


if __name__ == "__main__":
    main()
