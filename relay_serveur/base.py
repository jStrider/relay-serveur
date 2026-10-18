"""SQLite : un fichier, mode WAL, schéma créé à l'ouverture. Les blobs sont des octets opaques."""

import sqlite3

SCHEMA = """
create table if not exists comptes (
    id text primary key,
    jeton_hache blob not null,
    apns text,
    apns_env text,
    cree_le real not null,
    vu_le real not null,
    abonne_jusqu_au real,
    transaction_origine text
);
create table if not exists blobs (
    compte text not null references comptes(id) on delete cascade,
    nom text not null,
    contenu blob not null,
    taille integer not null,
    maj real not null,
    primary key (compte, nom)
);
create table if not exists reveils (
    compte text not null references comptes(id) on delete cascade,
    quand real not null
);
create index if not exists reveils_compte on reveils(compte, quand);
create index if not exists comptes_jeton on comptes(jeton_hache);
create unique index if not exists comptes_transaction on comptes(transaction_origine) where transaction_origine is not null;
"""


def ouvrir(chemin: str) -> sqlite3.Connection:
    """Connexion partagée par les threads du serveur (verrou côté SQLite, requêtes courtes)."""
    conn = sqlite3.connect(chemin, check_same_thread=False, isolation_level=None)
    conn.execute("pragma journal_mode=wal")
    conn.execute("pragma foreign_keys=on")
    conn.execute("pragma busy_timeout=5000")
    conn.executescript(SCHEMA)
    return conn
