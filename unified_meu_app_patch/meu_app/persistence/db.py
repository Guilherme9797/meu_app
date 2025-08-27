# persistence/db.py
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("APP_DB_PATH", "data/app.db")

SCHEMA = """
PRAGMA journal_mode=WAL;

-- ===== clientes =====
CREATE TABLE IF NOT EXISTS clientes (
  cliente_id TEXT PRIMARY KEY,
  nome       TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ===== contatos =====
CREATE TABLE IF NOT EXISTS contatos (
  phone      TEXT PRIMARY KEY,
  cliente_id TEXT NOT NULL,
  nome       TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT
);

-- ===== mensagens (histórico) =====
CREATE TABLE IF NOT EXISTS mensagens (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id TEXT NOT NULL,
  role       TEXT NOT NULL,   -- 'cliente' | 'assistente' | 'sistema'
  content    TEXT NOT NULL,
  meta       TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_msgs_cliente_created ON mensagens(cliente_id, created_at);

-- ===== propostas =====
CREATE TABLE IF NOT EXISTS propostas (
  id                TEXT PRIMARY KEY,
  cliente_id        TEXT NOT NULL,
  resumo            TEXT NOT NULL,
  texto             TEXT NOT NULL,
  preco_centavos    INTEGER NOT NULL,
  categoria_interna TEXT,
  moeda             TEXT NOT NULL DEFAULT 'BRL',
  status            TEXT NOT NULL DEFAULT 'draft',
  message_id        TEXT,
  enviada_em        TEXT,
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at        TEXT
);

CREATE TABLE IF NOT EXISTS propostas_eventos (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  proposta_id TEXT NOT NULL,
  tipo        TEXT NOT NULL,         -- 'created' | 'updated' | 'sent' | 'accepted' | etc.
  payload     TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ===== pagamentos =====
CREATE TABLE IF NOT EXISTS payments (
  id                  TEXT PRIMARY KEY,
  proposta_id         TEXT NOT NULL,
  amount_centavos     INTEGER NOT NULL,
  currency            TEXT NOT NULL DEFAULT 'BRL',
  provider            TEXT,
  provider_payment_id TEXT,
  checkout_url        TEXT,
  raw                 TEXT,
  status              TEXT NOT NULL DEFAULT 'pending',
  created_at          TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at          TEXT
);

CREATE TABLE IF NOT EXISTS payments_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  payment_id TEXT NOT NULL,
  provider   TEXT,
  event_type TEXT NOT NULL,
  payload    TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # permite dict(row) nos repositórios
    try:
        yield conn
    finally:
        conn.close()
