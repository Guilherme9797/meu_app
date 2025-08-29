import os, json, time, uuid, logging, unicodedata, traceback, re
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
from meu_app.models.cliente import Cliente
from meu_app.models.historico import HistoricoConversaPersistente
from meu_app.utils.openai_client import OpenAIClient, LLM
from meu_app.services.analisador import AnalisadorDeProblemas
from meu_app.services.buscador_pdf import BuscadorPDF
from meu_app.services.refinador import RefinadorResposta
from meu_app.services.atendimento import Atendimento
from meu_app.services.zapi_client import ZapiClient
from meu_app.services.conversor import ConversorPropostas
from meu_app.services.media_processor import MediaProcessor
from meu_app.persistence.db import init_db, get_conn
from meu_app.persistence.repositories import (
    ClienteRepository,
    ContatoRepository,
    PropostaRepository,
)
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
                base["trace"] = "".join(traceback.format_exception(*record.exc_info))[-4000:]
            else:
                base["trace"] = traceback.format_exc()[-4000:]
        except Exception:
            pass
    return json.dumps(base, ensure_ascii=False)

class _JSONHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = _json_log_format(record)
        except Exception:
            # último recurso
            msg = json.dumps(
                {
                    "ts": int(time.time() * 1000),
                    "level": record.levelname,
                    "msg": record.getMessage(),
                    "logger": record.name,
                },
                ensure_ascii=False,
            )
        self.stream.write(msg + "\n")
        self.flush()
root = logging.getLogger()
root.setLevel(logging.INFO)
logger = logging.getLogger(__name__)

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

def _hotfix_missing_autor_in_history(phone: str) -> int:
    """Tenta corrigir registros antigos sem 'autor' nas tabelas de histórico.
    Retorna quantidade de linhas afetadas (best-effort, silencioso em erro)."""
    affected = 0
    try:
        cid = None
        try:
            cr = ClienteRepository(); ctr = ContatoRepository()
            contato = ctr.get_by_phone(phone)
            if contato:
                cid = contato.get("cliente_id")
        except Exception:
            pass
        with get_conn() as conn:
            tabs = list(conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND lower(name) LIKE '%histor%'"))
            for (name,) in tabs:
                # checa colunas
                cols = [r[1].lower() for r in conn.execute(f"PRAGMA table_info({name})")]
                if "autor" not in cols:
                    continue
                try:
                    if cid is not None and "cliente_id" in cols:
                        cur = conn.execute(
                            f"UPDATE {name} SET autor = COALESCE(NULLIF(TRIM(autor), ''), 'cliente') WHERE cliente_id = ?",
                            (cid,),
                        )
                    else:
                        cur = conn.execute(
                            f"UPDATE {name} SET autor = COALESCE(NULLIF(TRIM(autor), ''), 'cliente') WHERE autor IS NULL OR TRIM(autor) = ''"
                        )
                    affected += cur.rowcount if hasattr(cur, "rowcount") else 0
                except Exception:
                    # ignora tabela incompatível
                    pass
    except Exception:
        pass
    return affected

app = Flask(__name__)

try:
    zapi_client = ZapiClient()
except RuntimeError:
    zapi_client = ZapiClient(instance_id="dummy", token="dummy")

llm = LLM()
media_processor = MediaProcessor(llm=llm)


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
            return jsonify(
                {
                    "status": "unsupported_media",
                    "reason": "Falha ao converter mídia em texto.",
                }
            ), 200

    if not computed_text:
        return jsonify({"status": "ignored", "reason": "Sem texto processável."}), 200

    logger.info(
        "Msg | client_id=%s | msg_id=%s | tipo=%s | texto=%r",
        normalized.client_id,
        normalized.msg_id,
        normalized.media_type or "text",
        computed_text[:120],
    )

    return jsonify(
        {
            "status": "ok",
            "client_id": normalized.client_id,
            "msg_id": normalized.msg_id,
            "media_type": normalized.media_type,
            "has_text": bool(computed_text),
        }
    )

def normalize_zapi_incoming(payload: dict) -> dict | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("type", "").lower() == "receivedcallback" or "text" in payload:
        phone = payload.get("phone")
        from_me = bool(payload.get("fromMe", False))
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
        return {"phone": phone, "text": text, "from_me": from_me}

    if "message" in payload:
        m = payload["message"]
        phone = m.get("from") or payload.get("from")
        body = None
        if isinstance(m, dict):
            body = (m.get("text") or {}).get("body") or m.get("body")
        return {"phone": phone, "text": body, "from_me": False}

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

    try:
        from meu_app.services.zapi_client import ZapiClient
        ZapiClient.from_env().send_text(phone, f"✅ Recebido: {text}")
    except Exception as e:
        app.logger.exception("Falha ao responder via Z-API: %s", e)

    return jsonify({"ok": True})

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

# ===== builders =====
def build_buscador() -> BuscadorPDF:
    return BuscadorPDF(
        openai_key=os.getenv("OPENAI_API_KEY"),
        tavily_key=os.getenv("TAVILY_API_KEY"),
        pdf_dir=os.getenv("PDFS_DIR", "data/pdfs"),
        index_dir=get_index_dir(),
    )

def build_atendimento_for_phone(phone: str, sender_name: Optional[str] = None) -> Atendimento:
    init_db()
    cr = ClienteRepository(); ctr = ContatoRepository()
    contato = ctr.get_by_phone(phone)
    if contato:
        cid = contato["cliente_id"]
        data = cr.obter(cid)
        nome = data["nome"] if data else (sender_name or f"Contato {phone}")
        cliente = Cliente(nome); cliente.id = cid
    else:
        nome = sender_name or f"Contato {phone}"
        cliente = Cliente(nome)
        cr.criar(cliente.id, cliente.nome, cliente.data_criacao)
        ctr.upsert(phone, cliente.id, nome=cliente.nome)
    oai = OpenAIClient(api_key=os.getenv("OPENAI_API_KEY"))
    analisador = AnalisadorDeProblemas(oai)
    buscador = build_buscador()
    refinador = RefinadorResposta(oai)
    return Atendimento(cliente, analisador, buscador, refinador, historico=HistoricoConversaPersistente(cliente.id))

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

# ===== request hooks =====
@app.before_request
def _before():
    g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
    g.t0 = time.perf_counter()

@app.after_request
def _after(resp):
    resp.headers["X-Request-Id"] = g.get("request_id", "")
    dt = int((time.perf_counter() - g.get("t0", time.perf_counter())) * 1000)
    logging.getLogger("access").info(
        json.dumps(
            {
                "request_id": g.get("request_id"),
                "method": request.method,
                "path": request.path,
                "status": resp.status_code,
                "duration_ms": dt,
            },
            ensure_ascii=False,
        )
    )
    metrics["requests_total"] += 1
    if resp.status_code >= 400:
        metrics["errors_total"] += 1
    return resp

# ===== health/metrics =====
@app.route("/health")
def health():
    checks = {}
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"error: {e}"
    has_index = os.path.exists(os.path.join(get_index_dir(), "index.faiss"))
    checks["faiss_index"] = "present" if has_index else "absent"
    checks["openai_key"] = "set" if os.getenv("OPENAI_API_KEY") else "missing"
    status = 200 if checks["db"] == "ok" else 500
    return jsonify({"status": "ok" if status == 200 else "degraded", "checks": checks}), status

@app.route("/metrics")
def metrics_route():
    body = "\n".join(
        "# HELP app_requests_total Total de requests\n"
        "# TYPE app_requests_total counter\n"
        f"app_requests_total {metrics['requests_total']}\n"
        "# HELP app_errors_total Total de erros\n"
        "# TYPE app_errors_total counter\n"
        f"app_errors_total {metrics['errors_total']}\n"
    ).strip()
    
    resp = make_response(body, 200)
    resp.headers["Content-Type"] = "text/plain; version=0.0.4"
    return resp

# ===== admin: índice =====
@app.route("/update-index", methods=["POST", "GET"])
@require_api_key
def update_index():
    if limiter:
        limiter.limit(os.getenv("RATE_LIMIT_ADMIN", "10 per minute"))(lambda: None)()
    buscador = build_buscador()
    m = buscador.atualizar_indice_verbose()
    return jsonify(m), 200

@app.route("/rebuild-index", methods=["POST", "GET"])
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

# ===== atendimento: ask =====
@app.route("/ask", methods=["POST"])
def ask():
    import logging
    log = logging.getLogger("server")

    data = request.get_json(force=True) or {}
    pergunta = data.get("pergunta") or ""
    phone = str(data.get("phone") or "0000000000")
    nome = data.get("nome") or "Cliente API"

    if not pergunta:
        return jsonify({"error": "Campo 'pergunta' é obrigatório"}), 400

    _ensure_ctx_defaults(phone, nome)

    atendimento = build_atendimento_for_phone(phone, nome)
    try:
        resposta = atendimento.receber_mensagem(pergunta)
    except KeyError as ke:
        if getattr(ke, "args", None) and len(ke.args) > 0 and ke.args[0] == "autor":
            log.warning("ask: KeyError 'autor' — aplicando default e reprocessando")
            _ensure_ctx_defaults(phone, nome)
            try:
                resposta = atendimento.receber_mensagem(pergunta)
            except KeyError as ke2:
                if getattr(ke2, "args", None) and len(ke2.args) > 0 and ke2.args[0] == "autor":
                    fixed = _hotfix_missing_autor_in_history(phone)
                    log.warning("ask: KeyError persistente — hotfix historico autor (linhas=%s)", fixed)
                    _ensure_ctx_defaults(phone, nome)
                    resposta = atendimento.receber_mensagem(pergunta)
                else:
                    raise
        else:
            raise

    return jsonify({"resposta": resposta}), 200

# ===== helpers: detecção de aceite =====
def _coerce_text(v) -> str:
    """Extrai texto de estruturas diversas de forma robusta."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, bytes):
        try:
            return v.decode().strip()
        except Exception:
            return v.decode("utf-8", errors="ignore").strip()
    if isinstance(v, dict):
        for key in ("text", "body", "message", "conversation"):
            if key in v:
                return _coerce_text(v[key])
        try:
            return json.dumps(v, ensure_ascii=False)
        except Exception:
            return str(v)
    if isinstance(v, (list, tuple, set)):
        return " ".join(_coerce_text(x) for x in v).strip()
    return str(v).strip()

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
    for g in gatilhos:
        if re.search(rf"\b{re.escape(g)}\b", m):
            # ignora expressões do tipo "não aceito" ou "nao pode seguir"
            if re.search(rf"(?:nao|não)\W*{re.escape(g)}", m):
                continue
            return True
    return False
# ===== webhook de recebimento (WhatsApp → Z-API) =====
@app.route("/conversao/aceite", methods=["POST"])
def conversao_aceite():
    data = request.get_json(force=True) or {}
    proposta_id = data.get("proposta_id")
    if not proposta_id:
        return jsonify({"error": "Informe 'proposta_id'"}), 400
    repo = PropostaRepository()
    if not repo.obter(proposta_id):
        return jsonify({"error": "Proposta não encontrada"}), 404
    repo.marcar_aceita(proposta_id)
    return jsonify({"status": "accepted", "proposta_id": proposta_id}), 200

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
    port = int(os.getenv("PORT", "5000"))

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



