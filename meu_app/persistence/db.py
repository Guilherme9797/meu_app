from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, ForeignKey, Text, JSON, Index, Float
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, scoped_session

# --------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------
DB_PATH = os.getenv("APP_DB_PATH", "data/app.db")
DB_URL = os.getenv("DB_URL", f"sqlite:///{DB_PATH}")

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
    future=True,
)
SessionLocal = scoped_session(
    sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
)
Base = declarative_base()

# --------------------------------------------------------------------
# Modelos novos (SQLAlchemy)
# --------------------------------------------------------------------
class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True)
    phone = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    status = Column(String(32), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("Session", back_populates="client")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    phase = Column(String(32), default="ATENDIMENTO")
    last_intent = Column(String(64), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", back_populates="sessions")
    messages = relationship("Message", back_populates="session", order_by="Message.id")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True, nullable=False)
    provider_msg_id = Column(String(128), nullable=True, index=True)
    role = Column(String(16), nullable=False)
    text = Column(Text, nullable=False)
    topic = Column(String(64), nullable=True)
    intent = Column(String(64), nullable=True)
    entities_json = Column(JSON, nullable=True)
    sources_json = Column(JSON, nullable=True)
    coverage = Column(Float, nullable=True)
    retrieval_scores_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="messages")


Index("ix_messages_provider_unique", Message.provider_msg_id, unique=False)

# --------------------------------------------------------------------
# Schema legado (compatibilidade com repositórios existentes)
# --------------------------------------------------------------------

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

# --------------------------------------------------------------------
# Bootstrapping
# --------------------------------------------------------------------
def init_db() -> None:
    """Cria tabelas caso não existam (uso simples)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_conn():
    """Compat: fornece conexão sqlite3 para repositórios legados."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_session():
    """Retorna sessão SQLAlchemy."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()