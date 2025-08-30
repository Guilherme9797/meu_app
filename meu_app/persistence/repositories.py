# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import uuid
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Optional, List

from .db import (
    get_conn,
    init_db,
    get_session,
    Client,
    Session as SessionModel,
    Message as MessageModel,
)


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ========= Clientes =========
class ClienteRepository:
    """
    Repositório de clientes.
    - criar(cliente_id, nome, created_at_iso=None): idempotente (IGNORE se já existir).
    - obter(cliente_id) -> dict|None
    """

    def __init__(self) -> None:
        init_db()

    def criar(self, cliente_id: str, nome: str, created_at_iso: Optional[str] = None) -> None:
        """
        created_at_iso: ISO8601 opcional (ex.: '2025-08-25T21:45:00').
        Se a coluna 'created_at' não existir no schema, faz fallback sem ela.
        """
        with get_conn() as con:
            try:
                if created_at_iso is not None:
                    # tenta inserir com created_at explícito
                    con.execute(
                        """
                        INSERT OR IGNORE INTO clientes (cliente_id, nome, created_at)
                        VALUES (?, ?, COALESCE(?, datetime('now')))
                        """,
                        (cliente_id, nome, created_at_iso),
                    )
                else:
                    # tenta inserir usando default do banco (se houver)
                    con.execute(
                        """
                        INSERT OR IGNORE INTO clientes (cliente_id, nome)
                        VALUES (?, ?)
                        """,
                        (cliente_id, nome),
                    )
            except sqlite3.OperationalError:
                # Fallback: schema sem 'created_at'
                con.execute(
                    "INSERT OR IGNORE INTO clientes (cliente_id, nome) VALUES (?, ?)",
                    (cliente_id, nome),
                )
            con.commit()

    def obter(self, cliente_id: str) -> Optional[Dict[str, Any]]:
        with get_conn() as con:
            row = con.execute(
                "SELECT * FROM clientes WHERE cliente_id = ?",
                (cliente_id,),
            ).fetchone()
            return dict(row) if row else None


# ========= Contatos =========
class ContatoRepository:
    def __init__(self) -> None:
        init_db()

    def get_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        with get_conn() as con:
            row = con.execute(
                "SELECT * FROM contatos WHERE phone = ?",
                (phone,),
            ).fetchone()
            return dict(row) if row else None

    def upsert(self, phone: str, cliente_id: str, nome: Optional[str] = None) -> None:
        with get_conn() as con:
            if nome is None:
                con.execute(
                    """
                    INSERT INTO contatos (phone, cliente_id)
                    VALUES (?, ?)
                    ON CONFLICT(phone) DO UPDATE SET
                      cliente_id = excluded.cliente_id,
                      updated_at = datetime('now')
                    """,
                    (phone, cliente_id),
                )
            else:
                con.execute(
                    """
                    INSERT INTO contatos (phone, cliente_id, nome)
                    VALUES (?, ?, ?)
                    ON CONFLICT(phone) DO UPDATE SET
                      cliente_id = excluded.cliente_id,
                      nome       = excluded.nome,
                      updated_at = datetime('now')
                    """,
                    (phone, cliente_id, nome),
                )
            con.commit()


# ========= Mensagens (histórico da conversa) =========
class MensagemRepository:
    """
    Histórico por cliente.
      - adicionar(cliente_id, role, content, meta=None) -> int
      - listar_por_cliente(cliente_id, limit=None, offset=0, asc=True) -> List[dict]
      - listar_ultimas(cliente_id, n=20) -> List[dict]
      - apagar_por_cliente(cliente_id) -> int
      - aliases: save, append, get_history
    """

    def __init__(self) -> None:
        init_db()

    def adicionar(
        self,
        cliente_id: str,
        role: str,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> int:
        with get_conn() as con:
            cur = con.execute(
                "INSERT INTO mensagens (cliente_id, role, content, meta) VALUES (?,?,?,?)",
                (
                    cliente_id,
                    role,
                    content,
                    json.dumps(meta, ensure_ascii=False) if meta is not None else None,
                ),
            )
            con.commit()
            return int(cur.lastrowid)

    # aliases
    def save(self, *args, **kwargs) -> int:
        return self.adicionar(*args, **kwargs)

    def append(self, *args, **kwargs) -> int:
        return self.adicionar(*args, **kwargs)

    def listar_por_cliente(
        self,
        cliente_id: str,
        limit: Optional[int] = None,
        offset: int = 0,
        asc: bool = True,
    ) -> List[Dict[str, Any]]:
        order = "ASC" if asc else "DESC"
        sql = f"""
            SELECT id, cliente_id, role, content, meta, created_at
              FROM mensagens
             WHERE cliente_id=?
             ORDER BY datetime(created_at) {order}
        """
        params: tuple[Any, ...]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params = (cliente_id, int(limit), int(offset))
        else:
            params = (cliente_id,)
        with get_conn() as con:
            cur = con.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
            for r in rows:
                try:
                    r["meta"] = json.loads(r["meta"]) if r.get("meta") else None
                except Exception:
                    pass
            return rows

    def listar_ultimas(self, cliente_id: str, n: int = 20) -> List[Dict[str, Any]]:
        with get_conn() as con:
            cur = con.execute(
                """
                SELECT id, cliente_id, role, content, meta, created_at
                  FROM mensagens
                 WHERE cliente_id=?
                 ORDER BY datetime(created_at) DESC
                 LIMIT ?
                """,
                (cliente_id, int(n)),
            )
            rows = [dict(r) for r in cur.fetchall()]
            rows.reverse()  # volta p/ ordem cronológica crescente
            for r in rows:
                try:
                    r["meta"] = json.loads(r["meta"]) if r.get("meta") else None
                except Exception:
                    pass
            return rows

    def get_history(self, cliente_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.listar_por_cliente(cliente_id, limit=limit, asc=True)

    def apagar_por_cliente(self, cliente_id: str) -> int:
        with get_conn() as con:
            cur = con.execute("DELETE FROM mensagens WHERE cliente_id=?", (cliente_id,))
            con.commit()
            return cur.rowcount


# ========= Propostas =========
class PropostaRepository:
    def __init__(self) -> None:
        init_db()

    def _evt(self, proposta_id: str, tipo: str, payload: Optional[Dict[str, Any]] = None) -> None:
        with get_conn() as con:
            con.execute(
                "INSERT INTO propostas_eventos (proposta_id, tipo, payload) VALUES (?,?,?)",
                (proposta_id, tipo, json.dumps(payload or {}, ensure_ascii=False)),
            )
            con.commit()

    def criar(
        self,
        *,
        cliente_id: str,
        resumo: str,
        texto: str,
        preco_centavos: int,
        categoria_interna: Optional[str] = None,
        moeda: str = "BRL",
    ) -> str:
        proposta_id = _gen_id("prop")
        with get_conn() as con:
            con.execute(
                """
                INSERT INTO propostas (id, cliente_id, resumo, texto, preco_centavos, categoria_interna, moeda, status)
                VALUES (?,?,?,?,?,?,?, 'draft')
                """,
                (proposta_id, cliente_id, resumo, texto, preco_centavos, categoria_interna, moeda),
            )
            con.commit()
        self._evt(proposta_id, "created", {"preco_centavos": preco_centavos})
        return proposta_id

    def obter(self, proposta_id: str) -> Optional[Dict[str, Any]]:
        with get_conn() as con:
            row = con.execute("SELECT * FROM propostas WHERE id=?", (proposta_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d.setdefault("proposta_id", d["id"])
            return d

    def atualizar_texto_preco(
        self,
        proposta_id: str,
        *,
        texto: str,
        preco_centavos: int,
        categoria_interna: Optional[str] = None,
    ) -> None:
        with get_conn() as con:
            if categoria_interna is None:
                con.execute(
                    "UPDATE propostas SET texto=?, preco_centavos=?, updated_at=datetime('now') WHERE id=?",
                    (texto, preco_centavos, proposta_id),
                )
            else:
                con.execute(
                    "UPDATE propostas SET texto=?, preco_centavos=?, categoria_interna=?, updated_at=datetime('now') WHERE id=?",
                    (texto, preco_centavos, categoria_interna, proposta_id),
                )
            con.commit()
        self._evt(proposta_id, "updated", {"preco_centavos": preco_centavos})

    def marcar_enviada(self, proposta_id: str, *, message_id: Optional[str]) -> None:
        with get_conn() as con:
            con.execute(
                "UPDATE propostas SET status='sent', enviada_em=datetime('now'), message_id=?, updated_at=datetime('now') WHERE id=?",
                (message_id, proposta_id),
            )
            con.commit()
        self._evt(proposta_id, "sent", {"message_id": message_id})

    def marcar_aceita(self, proposta_id: str) -> None:
        with get_conn() as con:
            con.execute(
                "UPDATE propostas SET status='accepted', updated_at=datetime('now') WHERE id=?",
                (proposta_id,),
            )
            con.commit()
        self._evt(proposta_id, "accepted", {})

    def eventos(self, proposta_id: str) -> List[Dict[str, Any]]:
        with get_conn() as con:
            cur = con.execute(
                "SELECT id, tipo, payload, created_at FROM propostas_eventos WHERE proposta_id=? ORDER BY id ASC",
                (proposta_id,),
            )
            rows = cur.fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                try:
                    d["payload"] = json.loads(d.get("payload") or "{}")
                except Exception:
                    pass
                out.append(d)
            return out

    def listar_por_cliente(self, cliente_id: str, *, status: Optional[str], limit: int, offset: int) -> List[Dict[str, Any]]:
        with get_conn() as con:
            if status:
                cur = con.execute(
                    "SELECT * FROM propostas WHERE cliente_id=? AND status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (cliente_id, status, limit, offset),
                )
            else:
                cur = con.execute(
                    "SELECT * FROM propostas WHERE cliente_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (cliente_id, limit, offset),
                )
            return [dict(r) for r in cur.fetchall()]

    def ultima_enviada_do_cliente(self, cliente_id: str) -> Optional[Dict[str, Any]]:
        with get_conn() as con:
            row = con.execute(
                "SELECT * FROM propostas WHERE cliente_id=? AND enviada_em IS NOT NULL ORDER BY datetime(enviada_em) DESC LIMIT 1",
                (cliente_id,),
            ).fetchone()
            return dict(row) if row else None


# ========= Pagamentos =========
class PaymentRepository:
    def __init__(self) -> None:
        init_db()

    def criar_pending(self, proposta_id: str, amount_centavos: int, currency: str, provider: str) -> str:
        payment_id = _gen_id("pay")
        with get_conn() as con:
            con.execute(
                "INSERT INTO payments (id, proposta_id, amount_centavos, currency, provider, status) VALUES (?,?,?,?,?, 'pending')",
                (payment_id, proposta_id, int(amount_centavos), currency or "BRL", provider),
            )
            con.commit()
        self._event(payment_id, provider, "created", {"amount_centavos": amount_centavos})
        return payment_id

    def set_checkout(self, payment_id: str, checkout_url: str, provider_payment_id: Optional[str], raw: Any) -> None:
        with get_conn() as con:
            con.execute(
                "UPDATE payments SET checkout_url=?, provider_payment_id=?, raw=?, updated_at=datetime('now') WHERE id=?",
                (
                    checkout_url,
                    str(provider_payment_id) if provider_payment_id else None,
                    json.dumps(raw, ensure_ascii=False) if raw is not None else None,
                    payment_id,
                ),
            )
            con.commit()
        self._event(
            payment_id,
            None,
            "checkout_created",
            {"checkout_url": checkout_url, "provider_payment_id": provider_payment_id},
        )

    def obter(self, payment_id: str) -> Optional[Dict[str, Any]]:
        with get_conn() as con:
            row = con.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
            return dict(row) if row else None

    def eventos(self, payment_id: str) -> List[Dict[str, Any]]:
        with get_conn() as con:
            cur = con.execute(
                "SELECT id, provider, event_type, payload, created_at FROM payments_events WHERE payment_id=? ORDER BY id ASC",
                (payment_id,),
            )
            out: List[Dict[str, Any]] = []
            for r in cur.fetchall():
                d = dict(r)
                try:
                    d["payload"] = json.loads(d.get("payload") or "{}")
                except Exception:
                    pass
                out.append(d)
            return out

    def marcar_paid(self, payment_id: str, paid_at_iso: Optional[str]) -> None:
        with get_conn() as con:
            con.execute(
                "UPDATE payments SET status='paid', updated_at=COALESCE(?, datetime('now')) WHERE id=?",
                (paid_at_iso, payment_id),
            )
            con.commit()
        self._event(payment_id, None, "paid", {"paid_at": paid_at_iso})

    def marcar_failed(self, payment_id: str, payload: Optional[Dict[str, Any]] = None) -> None:
        with get_conn() as con:
            con.execute(
                "UPDATE payments SET status='failed', updated_at=datetime('now') WHERE id=?",
                (payment_id,),
            )
            con.commit()
        self._event(payment_id, None, "failed", payload or {})

    def _event(self, payment_id: str, provider: Optional[str], event_type: str, payload: Dict[str, Any]) -> None:
        with get_conn() as con:
            con.execute(
                "INSERT INTO payments_events (payment_id, provider, event_type, payload) VALUES (?,?,?,?)",
                (payment_id, provider, event_type, json.dumps(payload, ensure_ascii=False)),
            )
            con.commit()


# ========= Auditoria genérica de webhooks (compat) =========
class WebhookLogRepository:
    pass
# ========= Novos repositórios (SQLAlchemy) =========


@contextmanager
def _session_scope() -> Any:
    with get_session() as db:
        yield db


class SessionRepository:
    """Operações relacionadas às sessões de atendimento."""

    def __init__(self) -> None:
        init_db()

    def get_or_create(self, client_phone: str) -> SessionModel:
        with _session_scope() as db:
            client = db.query(Client).filter_by(phone=client_phone).first()
            if not client:
                client = Client(phone=client_phone)
                db.add(client)
                db.flush()
            sess = (
                db.query(SessionModel)
                .filter_by(client_id=client.id)
                .order_by(SessionModel.id.desc())
                .first()
            )
            if not sess:
                sess = SessionModel(client_id=client.id)
                db.add(sess)
                db.flush()
            return sess

    def update_phase_if_ready(self, session_id: int, reply: str) -> None:
        with _session_scope() as db:
            sess = db.get(SessionModel, session_id)
            if not sess:
                return
            # lógica simplificada: placeholder para futuras regras
            db.add(sess)


class MessageRepository:
    """Persistência de mensagens de uma sessão."""

    def __init__(self) -> None:
        init_db()

    def exists_provider_msg(self, provider_msg_id: str) -> bool:
        if not provider_msg_id:
            return False
        with _session_scope() as db:
            return (
                db.query(MessageModel)
                .filter(MessageModel.provider_msg_id == provider_msg_id)
                .first()
                is not None
            )

    def save_in_out(
        self,
        *,
        session_id: int,
        provider_msg_id: Optional[str],
        user_msg: str,
        reply: str,
        topic: Optional[str],
        intent: Optional[str],
        entities: Dict[str, Any],
        sources: Optional[List[Dict[str, Any]]] = None,
        coverage: Optional[float] = None,
        retrieval_scores: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        with _session_scope() as db:
            user_entry = MessageModel(
                session_id=session_id,
                provider_msg_id=provider_msg_id,
                role="user",
                text=user_msg,
                topic=topic,
                intent=intent,
                entities_json=entities or None,
            )
            assist_entry = MessageModel(
                session_id=session_id,
                role="assistant",
                text=reply,
                topic=topic,
                intent=intent,
                sources_json=sources or None,
                coverage=coverage,
                retrieval_scores_json=retrieval_scores or None,
            )
            db.add_all([user_entry, assist_entry])

    def fetch_history_texts(self, session_id: int, limit: int = 10) -> List[Dict[str, str]]:
        """Retorna histórico recente da sessão."""
        with _session_scope() as db:
            rows = (
                db.query(MessageModel)
                .filter(MessageModel.session_id == session_id)
                .order_by(MessageModel.id.desc())
                .limit(limit)
                .all()
            )
            rows = list(reversed(rows))
            return [{"role": r.role, "text": r.text} for r in rows]
