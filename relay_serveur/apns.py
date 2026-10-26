"""Notifications APNs : silencieuses pour réveiller l'app, visibles pour les messages de l'agent. JWT ES256 en cache,
HTTP/2 vers l'hôte de l'environnement de l'appareil."""

import json
import time
from pathlib import Path

import httpx
import jwt

HOTES = {"sandbox": "api.sandbox.push.apple.com", "production": "api.push.apple.com"}


class Envoyeur:
    def __init__(self, config):
        self.config = config
        self._jeton = ""
        self._depuis = 0.0
        self._client = httpx.Client(http2=True, timeout=10)

    def jeton(self) -> str:
        if time.time() - self._depuis > 50 * 60:
            self._jeton = jwt.encode({"iss": self.config.apns_equipe, "iat": int(time.time())},
                                     Path(self.config.apns_cle).read_text(), algorithm="ES256",
                                     headers={"kid": self.config.apns_cle_id})
            self._depuis = time.time()
        return self._jeton

    def _poster(self, token: str, env: str, entetes: dict, corps: dict) -> int:
        """Code HTTP d'APNs ; 0 si l'envoi a échoué avant d'obtenir une réponse."""
        try:
            rep = self._client.post(
                f"https://{HOTES.get(env, HOTES['sandbox'])}/3/device/{token}",
                headers={"authorization": f"bearer {self.jeton()}", "apns-topic": self.config.apns_bundle, **entetes},
                content=json.dumps(corps))
            return rep.status_code
        except (httpx.HTTPError, OSError, ValueError):
            return 0

    def envoyer(self, token: str, env: str) -> int:
        return self._poster(token, env, {"apns-push-type": "background", "apns-priority": "5", "apns-expiration": "0"},
                            {"aps": {"content-available": 1}})

    def alerter(self, token: str, env: str, chiffre: str) -> int:
        """Notification visible : un texte générique, que l'extension de l'app remplace par le message déchiffré."""
        return self._poster(token, env, {"apns-push-type": "alert", "apns-priority": "10"},
                            {"aps": {"alert": {"loc-key": "MESSAGE_AGENT"}, "sound": "default", "mutable-content": 1}, "m": chiffre})
