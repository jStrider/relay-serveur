import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from relay_serveur import base as base_module
from relay_serveur.app import creer_app
from relay_serveur.config import Config


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(base=str(tmp_path / "relay.db"), gratuit=False)


@pytest.fixture
def base_tmp(config: Config) -> sqlite3.Connection:
    return base_module.ouvrir(config.base)


@pytest.fixture
def client(config: Config, base_tmp: sqlite3.Connection) -> TestClient:
    return TestClient(creer_app(config, base_tmp))
