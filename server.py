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
from meu_app.services.zapi_client import ZapiClient
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
        try:
            if isinstance(record.exc_info, tuple):
@@ -85,97 +82,57 @@ logger = logging.getLogger(__name__)
# Logger do werkzeug separado, para não conflitar no startup
wlog = logging.getLogger("werkzeug")
wlog.handlers = [logging.StreamHandler()]
wlog.setLevel(logging.INFO)
wlog.propagate = False
# ====== fim logger ======

# ===== helpers de contexto/compat =====
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

try:
    zapi_client = ZapiClient()
except RuntimeError:
    zapi_client = ZapiClient(instance_id="dummy", token="dummy")
@app.post("/webhook/zapi")
def zapi_webhook():
    raw_body = request.get_data()
    headers = {
        "x-hub-signature-256": request.headers.get("X-Hub-Signature-256", ""),
        "x-zapi-signature": request.headers.get("X-Zapi-Signature", ""),
        "x-z-api-signature": request.headers.get("X-Z-Api-Signature", ""),
    }
    if not zapi_client.verify_signature(raw_body, headers):
        return jsonify({"error": "Invalid signature"}), 401

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    try:
        normalized = zapi_client.parse_incoming(payload)
    except ValueError as e:
        return jsonify({"status": "ignored", "reason": str(e)}), 200

    computed_text = normalized.text
    if (not computed_text) and normalized.media_type in ("audio", "image") and normalized.media_url:
@@ -252,109 +209,103 @@ def normalize_zapi_incoming(payload: dict) -> dict | None:
            body = (m.get("text") or {}).get("body") or m.get("body")
        return {"phone": phone, "text": body, "from_me": False, "sender_name": sender_name}

    return None

@app.post("/zapi/webhook/received")
@app.post("/zapi/webhook/recebido")  # alias em PT-BR
def zapi_webhook_received():
    data = request.get_json(silent=True, force=True) or {}
    info = normalize_zapi_incoming(data)
    app.logger.info(f"[webhook] path={request.path} raw={str(data)[:800]}")
    app.logger.info(f"[webhook] norm={info}")

    if not info or not info.get("phone") or not info.get("text"):
        return jsonify({"ok": True, "ignored": True})

    if info.get("from_me"):
        return jsonify({"ok": True, "ignored": "from_me"})

    phone = info["phone"]
    text = info["text"].strip()
    sender_name = info.get("sender_name") or f"Contato {phone}"

    _ensure_ctx_defaults(phone, sender_name)
    try:
        resposta = atendimento_service.handle_incoming(phone, text)
    except Exception as e:
        app.logger.exception("Falha no processamento da mensagem: %s", e)
        resposta = "Desculpe, ocorreu um erro ao processar sua mensagem."

    try:
        zapi_client.send_message(phone, resposta)
        sent = True
    except Exception as e:
        sent = False
        app.logger.exception("Falha ao responder via Z-API: %s", e)

    return jsonify({"ok": True, "client_id": phone, "msg_id": info.get("msg_id"), "sent": sent})

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
media_processor = MediaProcessor(llm=llm)

# ===== auth admin =====
def require_api_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        required = os.getenv("ADMIN_API_KEY")
        # aceita X-API-Key, Authorization: Bearer, ou ?api_key
        provided = (
            request.headers.get("X-API-Key")
            or (
                request.headers.get("Authorization", "").split(" ", 1)[-1]
                if request.headers.get("Authorization", "").lower().startswith("bearer ")
                else None
            )
            or request.args.get("api_key")
        )
        if not required:
            return jsonify({"error": "ADMIN_API_KEY não configurado"}), 500
        if not provided or provided != required:
            return jsonify({"error": "unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper

metrics = {"requests_total": 0, "errors_total": 0}

@@ -431,121 +382,70 @@ def update_index():
@require_api_key
def rebuild_index():
    if limiter:
        limiter.limit(os.getenv("RATE_LIMIT_ADMIN", "10 per minute"))(lambda: None)()
    buscador = build_buscador()
    m = buscador.indexador.indexar_pdfs()
    return jsonify(m), 200

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
    zc = ZapiClient()
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
        s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    except Exception:
        s = str(s)
    return s.lower().strip()

def _is_aceite_text(msg) -> bool:
    m = _normalize_text(msg)
    gatilhos = [
        "aceito", "fechado", "vamos fechar", "ok pode seguir", "pode seguir",
        "contratar", "concordo", "vamos sim", "ok, pode ser", "podemos seguir",
    ]
    return any(g in m for g in gatilhos)

# ===== Z-API: rotas compatíveis/fallbacks =====
@app.route("/webhook", methods=["POST"])
def webhook_alias():
    # algumas contas de Z-API usam /webhook — reusa o handler
    return zapi_webhook_received()

@app.route("/zapi/webhook/delivery", methods=["POST"])
def zapi_webhook_delivery():
    try:
        if limiter:
            limiter.limit(os.getenv("RATE_LIMIT_WEBHOOK", "60 per minute"))(lambda: None)()
    except Exception:
        pass
    try:
        payload = request.get_json(force=True) or {}
        app.logger.info("delivery webhook: %s", json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass
    return jsonify({"status": "ok"}), 200

# ===== main =====
if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", "5050"))
    if os.getenv("NGROK_AUTHTOKEN") or os.getenv("NGROK_DOMAIN"):
        try:
            from pyngrok import ngrok

            token = os.getenv("NGROK_AUTHTOKEN")
            if token:
                ngrok.set_auth_token(token)

            domain = os.getenv("NGROK_DOMAIN")
            kwargs = {"bind_tls": True}
            if domain:
                 kwargs["domain"] = domain

            url = ngrok.connect(addr=port, proto="http", **kwargs).public_url
            print(f"[ngrok] público: {url}")
        except Exception as exc:
            print(f"[ngrok] erro ao iniciar: {exc}")

    app.run(host="0.0.0.0", port=port)



