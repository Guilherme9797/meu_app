import os, json, time, uuid, logging, unicodedata, traceback
from functools import wraps
from typing import Optional
from flask import Flask, jsonify, request, g, make_response, has_request_context

try:
    from flask_cors import CORS
except Exception:
    CORS = None
try:
    from flask_limiter import Limiter
except Exception:
    Limiter = None

# ===== imports do domínio (use o pacote "meu_app") =====
from meu_app.utils.openai_client import Embeddings, LLM
from meu_app.services.buscador_pdf import Retriever
from meu_app.services.tavily_service import TavilyClient
from meu_app.services.refinador import GroundingGuard
from meu_app.services.analisador import Classifier, Extractor
from meu_app.persistence.repositories import (
    SessionRepository,
    MessageRepository,
)
from meu_app.services.atendimento import AtendimentoService, AtendimentoConfig
from meu_app.services.zapi_client import ZApiClient, NormalizedMessage  # <-- corrige nome da classe
from meu_app.services.media_processor import MediaProcessor
from meu_app.persistence.db import init_db, get_conn
from meu_app.utils.paths import get_index_dir

# ====== JSON logger “safe” (único) ======
def _json_log_format(record: logging.LogRecord) -> str:
    base = {
        "ts": int(time.time() * 1000),
        "level": record.levelname,
        "msg": record.getMessage(),
        "logger": record.name,
    }
    if has_request_context():
        try:
            rid = getattr(g, "request_id", None)
            if rid:
                base["request_id"] = rid
            base["path"] = request.path
            base["method"] = request.method
            base["remote_ip"] = request.headers.get("X-Forwarded-For", request.remote_addr)
        except Exception:
            pass
    # inclui traceback compacto quando houver exceção
    if record.exc_info:
        base["exc_info"] = True
    return json.dumps(base, ensure_ascii=False)

def _ensure_ctx_defaults(phone: str, sender_name: str) -> dict:
    """Garante g.autor, g.webhook_ctx e g.ctx com 'autor'."""
    try:
        g.autor = getattr(g, "autor", "cliente") or "cliente"
        wctx = getattr(g, "webhook_ctx", None) or {}
        if not isinstance(wctx, dict):
            wctx = {}
        if "autor" not in wctx or not wctx.get("autor"):
            wctx["autor"] = "cliente"
        wctx["phone"] = phone
        wctx["sender_name"] = sender_name
        g.webhook_ctx = wctx
        g.ctx = wctx
        return wctx
    except Exception:
        return {"autor": "cliente", "phone": phone, "sender_name": sender_name}

app = Flask(__name__)

# logger de módulo apontando para o logger do app (evita NameError em logger.info)
logger = app.logger

try:
    zapi_client = ZApiClient()
except RuntimeError:
    # mantém fallback, apenas com o nome correto da classe
    zapi_client = ZApiClient()  # se seu __init__ exigir params, ajuste nas envs

def normalize_zapi_incoming(payload: dict) -> dict | None:
    if not isinstance(payload, dict):
        return None

    if payload.get("type", "").lower() == "receivedcallback" or "text" in payload:
        phone = payload.get("phone")
        from_me = bool(payload.get("fromMe", False))
        sender_name = payload.get("senderName") or payload.get("chatName")
        text = None
        txt = payload.get("text")
        if isinstance(txt, dict):
            text = txt.get("message")
        if not text:
            img = payload.get("image") or {}
            if isinstance(img, dict):
                text = img.get("caption")
        if not text:
            doc = payload.get("document") or {}
            if isinstance(doc, dict):
                text = doc.get("title") or doc.get("fileName")
        return {"phone": phone, "text": text, "from_me": from_me, "sender_name": sender_name}

    if "message" in payload:
        m = payload["message"]
        phone = m.get("from") or payload.get("from")
        sender_name = payload.get("senderName") or payload.get("chatName")
        body = None
        if isinstance(m, dict):
            body = (m.get("text") or {}).get("body") or m.get("body")
        return {"phone": phone, "text": body, "from_me": False, "sender_name": sender_name}

    return None

@app.post("/zapi/webhook/received")
@app.post("/zapi/webhook/recebido")  # alias em PT-BR
def zapi_webhook_received():
    data = request.get_json(silent=True, force=True) or {}
    app.logger.info(f"[webhook] path={request.path} raw={str(data)[:800]}")
    try:
        normalized = zapi_client.parse_incoming(data)
    except ValueError:
        info = normalize_zapi_incoming(data)
        app.logger.info(f"[webhook] norm={info}")
        if not info or not info.get("phone") or not info.get("text"):
            return jsonify({"ok": True, "ignored": True})
        normalized = NormalizedMessage(
            client_id=info["phone"],
            text=info.get("text"),
            msg_id=None,
            timestamp=None,
        )
    if normalized.client_id is None:
        return jsonify({"ok": True, "ignored": True})
    computed_text = normalized.text
    if (not computed_text) and normalized.media_type in ("audio", "image") and normalized.media_url:
        try:
            computed_text = media_processor.process_media_to_text(
                media_url=normalized.media_url,
                media_type=normalized.media_type,
                media_mime=normalized.media_mime,
                caption=normalized.media_caption,
            )
            logger.info(
                "Texto derivado de %s obtido com sucesso (%d chars).",
                normalized.media_type,
                len(computed_text or ""),
            )
        except Exception as e:
            logger.exception("Falha ao processar mídia: %s", e)
            return jsonify({"ok": True, "ignored": "media_error"})
    if not computed_text:
        return jsonify({"ok": True, "ignored": True})

    phone = normalized.client_id
    sender_name = "Contato"
    _ensure_ctx_defaults(phone, sender_name)

    try:
        resposta = atendimento_service.handle_incoming(phone, computed_text)
    except Exception as e:
        app.logger.exception("Falha no processamento da mensagem: %s", e)
        resposta = "Desculpe, ocorreu um erro ao processar sua mensagem."

    try:
        zapi_client.send_message(phone, resposta)
        sent = True
    except Exception as e:
        sent = False
        app.logger.exception("Falha ao responder via Z-API: %s", e)
    return jsonify({"ok": True, "client_id": phone, "msg_id": normalized.msg_id, "sent": sent})

log = app.logger
log.setLevel(logging.INFO)

# ===== CORS / Rate limit =====
allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if CORS and allowed_origins:
    CORS(app, resources={r"/*": {"origins": allowed_origins}})

limiter = None
if Limiter:
    limiter = Limiter(
        app=app,
        key_func=lambda: request.headers.get("X-Forwarded-For", request.remote_addr),
        default_limits=[os.getenv("RATE_LIMIT_DEFAULT", "60 per minute")],
    )

# ===== inicialização global =====
init_db()
embedder = Embeddings()
retriever = Retriever(index_path=os.getenv("RAG_INDEX_PATH", "index/faiss_index"), embed_fn=embedder.embed)
tavily = TavilyClient()
llm = LLM()
guard = GroundingGuard()
classifier = Classifier()
extractor = Extractor()

# instancia o MediaProcessor (era usado mas não existia -> NameError)
media_processor = MediaProcessor(llm=llm)

# instancia o AtendimentoService (era usado mas não existia -> NameError)
sess_repo = SessionRepository()
msg_repo = MessageRepository()
config = AtendimentoConfig()

atendimento_service = AtendimentoService(
    sess_repo=sess_repo,
    msg_repo=msg_repo,
    retriever=retriever,
    tavily=tavily,
    llm=llm,
    guard=guard,
    classifier=classifier,
    extractor=extractor,
    conf=config,
)

@app.route("/health")
def health():
    checks = {"db": "ok"}
    try:
        conn = get_conn()
        _ = conn.execute("SELECT 1").fetchone()
        checks["db"] = "ok"
    except Exception:
        checks["db"] = "fail"
    status = 200 if checks["db"] == "ok" else 500
    return jsonify({"status": "ok" if status == 200 else "degraded", "checks": checks}), status

@app.route("/metrics")
def metrics_route():
    body = "\n".join(
        [
            "# HELP app_requests_total Total de requests",
            "# TYPE app_requests_total counter",
            f"app_requests_total {metrics['requests_total']}",
            "# HELP app_errors_total Total de erros",
            "# TYPE app_errors_total counter",
            f"app_errors_total {metrics['errors_total']}",
        ]
    )
    resp = make_response(body, 200)
    resp.headers["Content-Type"] = "text/plain; version=0.0.4"
    return resp

# ===== admin: índice =====
@app.route("/update-index", methods=["POST", "GET"])
@require_api_key
def update_index():
    if limiter:
        limiter.limit(os.getenv("RATE_LIMIT_ADMIN", "10 per minute"))(lambda: None)()
    from meu_app.services.pdf_indexer import build_index
    build_index(
        src_dir=os.getenv("PDF_SRC_DIR", "data/pdfs"),
        out_dir=os.getenv("RAG_INDEX_PATH", get_index_dir()),
        model=os.getenv("EMBED_MODEL", "text-embedding-3-small"),
    )
    return jsonify({"status": "rebuilt"}), 200

# ===== Z-API: configurar webhooks =====
@app.route("/zapi/configure-webhooks", methods=["POST"])
@require_api_key
def zapi_configure_webhooks():
    if limiter:
        limiter.limit(os.getenv("RATE_LIMIT_ADMIN", "10 per minute"))(lambda: None)()
    data = request.get_json(silent=True) or {}
    received_url = data.get("received_url") or os.getenv("ZAPI_WEBHOOK_RECEIVED_URL")
    delivery_url = data.get("delivery_url") or os.getenv("ZAPI_WEBHOOK_DELIVERY_URL")
    if not received_url:
        return jsonify({"error": "Informe 'received_url'"}), 400
    zc = ZApiClient()  # <-- corrige nome aqui também
    out = {"received": zc.update_webhook_received(received_url)}
    if delivery_url:
        out["delivery"] = zc.update_webhook_delivery(delivery_url)
    return jsonify(out), 200

# ===== helpers: detecção de aceite =====
def _normalize_text(s) -> str:
    # robusto para qualquer tipo (usa _coerce_text quando necessário)
    if not isinstance(s, str):
        s = _coerce_text(s)
    s = s or ""
    try:
        s = unicodedata.normalize("NFKC", s)
    except Exception:
        pass
    return s.strip()
