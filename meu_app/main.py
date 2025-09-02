#!/usr/bin/env python
# main.py — CLI da Etapa 1+2 (Atendimento + Conversão, com desconto controlado)
from __future__ import annotations

import os
import sys
import json
import time
import argparse
import datetime as dt
import logging
from typing import Optional, Dict, Any, List
import math

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


logging.basicConfig(
    level=os.getenv("LOGLEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from meu_app.utils.paths import get_index_dir
from meu_app.utils.openai_client import Embeddings, LLM
from meu_app.services import (
    Classifier,
    Extractor,
    Retriever,
    GroundingGuard,
    TavilyClient,
   
)

from meu_app.persistence.repositories import SessionRepository, MessageRepository

# -------------------------------------------------------------------------
# Suporte para execução direta OU como módulo (-m meu_app.main)
# -------------------------------------------------------------------------
if __package__ is None or __package__ == "":
    # Execução direta: injeta o diretório-pai que contém "meu_app" no sys.path
    _here = os.path.abspath(__file__)
    _pkg_dir = os.path.dirname(_here)                  # .../meu_app
    _project_root = os.path.dirname(_pkg_dir)          # diretório que CONTÉM "meu_app"
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from meu_app.persistence.db import init_db
    from meu_app.persistence.repositories import (
        ClienteRepository,
        ContatoRepository,
        PropostaRepository,
    )
    from meu_app.models import Cliente, HistoricoConversaPersistente
    from meu_app.utils import OpenAIClient
    from meu_app.services import (
        AnalisadorDeProblemas,
        BuscadorPDF,
        PDFIndexer,
        RefinadorResposta,
        Atendimento,
        ConversorPropostas,
    )
    try:
        from meu_app.services.pricing import PricingService, PricingInput  # noqa: F401
    except Exception:
        PricingService = None  # type: ignore
        PricingInput = None    # type: ignore
else:
    # Execução como pacote
    from .persistence.db import init_db
    from .persistence.repositories import (
        ClienteRepository,
        ContatoRepository,
        PropostaRepository,
    )
    from .models import Cliente, HistoricoConversaPersistente
    from .utils import OpenAIClient
    from .services import (
        AnalisadorDeProblemas,
        BuscadorPDF,
        PDFIndexer,
        RefinadorResposta,
        Atendimento,
        ConversorPropostas,
    )
    try:
        from .services.pricing import PricingService, PricingInput  # noqa: F401
    except Exception:
        PricingService = None  # type: ignore
        PricingInput = None    # type: ignore


# -----------------------------------------------------------------------------
# Helpers básicos
# -----------------------------------------------------------------------------
def _now_iso() -> str:
    return dt.datetime.utcnow().isoformat(timespec="seconds")


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _fmt_brl(valor: float) -> str:
    try:
        # formatação simples PT-BR
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"R$ {valor:.2f}"

def _round_up(x: float, step: int) -> float:
    """Arredonda ``x`` para cima no múltiplo de ``step`` mais próximo."""
    step = max(1, int(step))
    return math.ceil(x / step) * step

def _ensure_openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("❌ Defina OPENAI_API_KEY no ambiente (.env) para usar esta função.", file=sys.stderr)
        sys.exit(2)
    return key


def _make_oai() -> OpenAIClient:
    key = _ensure_openai_key()
    model = os.getenv("OPENAI_MODEL") or os.getenv("OPENAI_CHAT_MODEL") or "gpt-4o-mini"
    temp = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
    return OpenAIClient(api_key=key, chat_model=model, temperature=temp)


def _build_buscador() -> BuscadorPDF:
    return BuscadorPDF(
        openai_key=os.getenv("OPENAI_API_KEY"),
        tavily_key=os.getenv("TAVILY_API_KEY"),
        pdf_dir=os.getenv("PDFS_DIR", "data/pdfs"),
        index_dir=os.getenv("INDEX_DIR", "index/faiss_index"),
    )


def get_index_dir() -> str:
    """Retorna o diretório do índice FAISS (padrão em env INDEX_DIR)."""
    return os.getenv("INDEX_DIR", "index/faiss_index")

def _dispatch(service, phone, text):
    """Tenta diversas convenções de handler para despachar a mensagem."""
    for name in (
        "handle_incoming",
        "receber_mensagem",
        "handle_message",
        "responder",
        "handle",
        "chat",
        "process",
        "run",
        "__call__",
    ):
        fn = getattr(service, name, None)
        if callable(fn):
            try:
                return fn(phone, text)
            except TypeError:
                try:
                    return fn(text)
                except TypeError:
                    continue
    raise AttributeError(
        f"Handler compatível não encontrado em {service.__class__.__name__}."
    )


def _build_atendimento_service() -> AtendimentoService:
    """Instancia o pipeline completo de atendimento."""
    from meu_app.services.atendimento import AtendimentoService, AtendimentoConfig
    try:
        from meu_app.services.retriever import Embeddings, Retriever  # type: ignore
    except Exception:  # fallback simplificado
        class Embeddings:  # type: ignore
            def embed(self, *a, **kw):
                return []

        class Retriever:  # type: ignore
            def __init__(self, *a, **kw):
                pass

            def retrieve(self, *a, **kw):
                return []
    try:
        from tavily import TavilyClient  # type: ignore
    except Exception:  # pragma: no cover - opcional
        TavilyClient = None  # type: ignore
    
     # Usa o cliente real de LLM baseado em OpenAI, com fallback leve em ambientes
    # onde o módulo ou as credenciais não estejam disponíveis. O AtendimentoService
    # espera métodos como ``generate``/``chat``/``complete``.
    try:
        from meu_app.utils.openai_client import LLM as OpenAILLM  # type: ignore
    except Exception:
        class LLM:  # type: ignore
            def chat(self, *a, **kw):
                return "Desculpe, não consegui gerar uma resposta agora."
        OpenAILLM = None  # type: ignore

    class _StubLLM:  # type: ignore
        def generate(self, *a, **kw):
            return "Desculpe, não consegui gerar uma resposta agora."

        def chat(self, *a, **kw):
            return "Desculpe, não consegui gerar uma resposta agora."

        def complete(self, *a, **kw):
            return "Desculpe, não consegui gerar uma resposta agora."
    try:
        from meu_app.services.guard import GroundingGuard  # type: ignore
    except Exception:
        class GroundingGuard:  # type: ignore
            def check(self, *a, **kw):
                return {"allowed": True}
    try:
        from meu_app.services.classifier import Classifier  # type: ignore
    except Exception:
        class Classifier:  # type: ignore
            def classify(self, *a, **kw):
                return None
    try:
        from meu_app.services.extractor import Extractor  # type: ignore
    except Exception:
        class Extractor:  # type: ignore
            def extract(self, *a, **kw):
                return {}
    try:
        from meu_app.persistence.repositories import SessionRepository, MessageRepository  # type: ignore
    except Exception:
        class SessionRepository:  # type: ignore
            def __init__(self, *a, **kw):
                pass

        class MessageRepository:  # type: ignore
            def __init__(self, *a, **kw):
                pass

            def save(self, *a, **kw):
                pass

    embedder = Embeddings()
    retriever = Retriever(index_path=get_index_dir(), embed_fn=getattr(embedder, "embed", lambda x: []))
    tavily = None
    api_key = os.getenv("TAVILY_API_KEY")
    if api_key and TavilyClient:
        try:
            tavily = TavilyClient(api_key=api_key)
        except Exception as e:
            logging.exception("Falha ao instanciar TavilyClient: %s", e)
            tavily = None
    llm = _StubLLM()
    if OpenAILLM is not None:
        try:
            llm = OpenAILLM()
        except Exception:
            llm = _StubLLM()
    logging.getLogger(__name__).info("LLM selecionado: %s", type(llm).__name__)
    if type(llm).__name__ in {"_StubLLM", "LLMStub"}:
        raise RuntimeError(
            "LLM real não inicializado. Verifique OPENAI_API_KEY/OPENAI_MODEL e o pacote 'openai'."
        )
    GG = GroundingGuard
    try:
        guard = GG() if callable(GG) else GG
    except Exception:
        class _NoopGuard:
            def check(self, *a, **kw):
                return {"allowed": True, "reason": "noop"}

        guard = _NoopGuard()
    classifier = Classifier()
    extractor = Extractor()
    sess_repo = SessionRepository()
    msg_repo = MessageRepository()
    conf = AtendimentoConfig(use_web=tavily is not None, append_low_coverage_note=False)
    return AtendimentoService(
        sess_repo=sess_repo,
        msg_repo=msg_repo,
        retriever=retriever,
        tavily=tavily,
        llm=llm,
        guard=guard,
        classifier=classifier,
        extractor=extractor,
        conf=conf,
    )


def _build_atendimento_for(phone: Optional[str], nome: str) -> Atendimento:
    """
    Reutiliza cliente existente pelo phone (se informado); senão cria novo cliente.
    """
    init_db()
    cliente_repo = ClienteRepository()
    contato_repo = ContatoRepository()

    if phone:
        ctt = contato_repo.get_by_phone(phone)
        if ctt:
            cliente_data = cliente_repo.obter(ctt["cliente_id"])
            nome_final = (cliente_data["nome"] if cliente_data else nome) or f"Contato {phone}"
            cliente = Cliente(nome_final)
            cliente.id = ctt["cliente_id"]  # preserva ID persistido
        else:
            # novo cliente associado a este phone
            cliente = Cliente(nome or f"Contato {phone}")
            cliente_repo.criar(cliente.id, cliente.nome, _now_iso())
            contato_repo.upsert(phone, cliente.id, nome=cliente.nome)
    else:
        # sem phone: cria um cliente novo (sessão efêmera)
        cliente = Cliente(nome or "Cliente CLI")
        cliente_repo.criar(cliente.id, cliente.nome, _now_iso())

def _resolve_cliente_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    """Busca informações do cliente associado ao ``phone``.

    Retorna um dicionário com dados do contato e do cliente ou ``None``
    se o número não estiver cadastrado.
    """
    init_db()
    contato_repo = ContatoRepository()
    cliente_repo = ClienteRepository()
    contato = contato_repo.get_by_phone(phone)
    if not contato:
        return None
    cliente = cliente_repo.obter(contato["cliente_id"])
    info: Dict[str, Any] = dict(contato)
    info["cliente"] = cliente
    return info

# -----------------------------------------------------------------------------
# Comandos: Atendimento
# -----------------------------------------------------------------------------


def cmd_ask(args):
    _ensure_openai_key()
    atendimento = _build_atendimento_for(args.phone, args.nome)
    pergunta = (args.pergunta or "").strip()
    if not pergunta:
        print("❌ Informe a pergunta (flag --pergunta).", file=sys.stderr)
        sys.exit(2)
    print(f"👤 {atendimento.cliente.nome}: {pergunta}")
    t0 = time.perf_counter()
    resposta = atendimento.receber_mensagem(pergunta)
    dt_s = round(time.perf_counter() - t0, 2)
    print(f"\n🤖 Assistente ({dt_s}s):\n{resposta}\n")


def cmd_chat(args):
    _ensure_openai_key()
    atendimento = _build_atendimento_service()
    print("💬 Chat interativo — digite sua mensagem. Comandos: /sair, /fim")
    print(f"Cliente: {args.nome} | Phone: {args.phone or 'anon'}")
    try:
        while True:
            msg = input("\n👤 Você: ").strip()
            if not msg:
                continue
            if msg.lower() in {"/sair", "/fim", "/exit", "/quit"}:
                print("👋 Encerrando chat.")
                break
            t0 = time.perf_counter()
            try:
                resposta = _dispatch(atendimento, args.phone or "anon", msg)
            except Exception:
                import traceback
                print("\n[ERRO] Ocorreu uma exceção no atendimento. Veja logs e continue.")
                traceback.print_exc()
                continue
            dt_s = round(time.perf_counter() - t0, 2)
            print(f"\n🤖 Assistente ({dt_s}s):\n{resposta}")
    except (KeyboardInterrupt, EOFError):
        print("\n👋 Encerrado.")

# -----------------------------------------------------------------------------
# Comando: Z-API webhooks
# -----------------------------------------------------------------------------
def cmd_configure_webhooks(args):
    url = args.received_url or os.getenv("ZAPI_WEBHOOK_RECEIVED_URL")
    if not url:
        print("❌ Informe --received-url ou defina ZAPI_WEBHOOK_RECEIVED_URL.", file=sys.stderr)
        sys.exit(2)
    try:
        # carregamento tardio para não forçar dependência
        if __package__ in (None, ""):
            from meu_app.services.zapi_client import ZapiClient  # type: ignore
        else:
            from .services.zapi_client import ZapiClient  # type: ignore
        zc = ZapiClient()
    except Exception as e:
        print(f"❌ Erro ao inicializar ZapiClient: {e}", file=sys.stderr)
        sys.exit(1)
    out = {"received": zc.update_webhook_received(url)}
    if args.delivery_url or os.getenv("ZAPI_WEBHOOK_DELIVERY_URL"):
        out["delivery"] = zc.update_webhook_delivery(args.delivery_url or os.getenv("ZAPI_WEBHOOK_DELIVERY_URL"))
    _print_json(out)

# -----------------------------------------------------------------------------
# Comandos: Conversão (propostas)
# -----------------------------------------------------------------------------
def _build_conversor() -> ConversorPropostas:
    buscador = _build_buscador()
    oai = _make_oai()
    return ConversorPropostas(oai, buscador)


def cmd_proposta_preview(args):
    init_db()
    conv = _build_conversor()
    resumo = args.resumo
    texto = conv.preview(args.nome, resumo, valor_economico_brl=args.valor)
    out = {
        "preco_brl": texto.preco_reais,
        "preco_fmt": _fmt_brl(texto.preco_reais),
        "categoria_interna": getattr(texto, "categoria_interna", None),
        "texto": texto.texto,
    }
    _print_json(out)


def cmd_proposta_send(args):
    init_db()
    conv = _build_conversor()
    repo = PropostaRepository()

    resumo = args.resumo
    texto = conv.preview(args.nome, resumo, valor_economico_brl=args.valor)

    # determina cliente_id de forma segura
    if args.phone:
        info = _resolve_cliente_by_phone(args.phone) or {}
        cliente_id = info.get("cliente_id", "sem_phone")
    else:
        cliente_id = "sem_phone"

    # cria proposta na base
    proposta_id = repo.criar(
        cliente_id=cliente_id,
        resumo=resumo,
        texto=texto.texto,
        preco_centavos=int(round(texto.preco_reais * 100)),
        categoria_interna=getattr(texto, "categoria_interna", None),
        moeda="BRL",
    )

    # tenta enviar via Z-API (opcional)
    message_id = None
    try:
        if __package__ in (None, ""):
            from meu_app.services.zapi_client import ZapiClient  # type: ignore
        else:
            from .services.zapi_client import ZapiClient  # type: ignore
        if args.phone:
            zc = ZapiClient()
            body = f"Olá {args.nome}!\n\n{texto.texto}\n\nPreço sugerido: {_fmt_brl(texto.preco_reais)}"
            resp = zc.send_text(args.phone, body)  # depende da sua implementação
            if isinstance(resp, dict):
                message_id = (
                    resp.get("id")
                    or resp.get("messageId")
                    or resp.get("message_id")
                )
            else:
                message_id = resp
            if message_id is not None and not isinstance(message_id, str):
                message_id = str(message_id)
    except Exception:
        pass  # sem Z-API configurada, segue sem enviar

    repo.marcar_enviada(proposta_id, message_id=message_id)
    _print_json({"proposta_id": proposta_id, "enviada": True, "message_id": message_id})


def cmd_proposta_discount(args):
    init_db()
    repo = PropostaRepository()
    prop = repo.obter(args.proposta_id)
    if not prop:
        print("❌ Proposta não encontrada.", file=sys.stderr)
        sys.exit(2)

    # preço atual
    preco_atual = float(prop.get("preco_centavos", 0) or 0) / 100.0

    # aplica estratégia simples de desconto
    if args.target is not None:
        novo_preco = float(args.target)
    elif args.percent and args.percent > 0:
        novo_preco = preco_atual * (1.0 - (float(args.percent) / 100.0))
    else:
        # sem alteração de preço; se veio --valor (econômico), pode-se recalcular piso via modelo no futuro
        novo_preco = preco_atual

    # arredonda em múltiplos de 5 reais
    novo_preco = _round_up(novo_preco, 5)

    # atualiza texto/preço (mantém texto salvo; se veio um resumo novo, só registra evento)
    repo.atualizar_texto_preco(args.proposta_id, texto=prop.get("texto", ""), preco_centavos=int(round(novo_preco * 100)))
    if args.resumo:
        # registra um evento informativo (se quiser persistir, adapte seu repo)
        pass

    # reenviar se solicitado
    info_envio: Dict[str, Any] = {}
    if args.resend and args.phone:
        try:
            if __package__ in (None, ""):
                from meu_app.services.zapi_client import ZapiClient  # type: ignore
            else:
                from .services.zapi_client import ZapiClient  # type: ignore
            zc = ZapiClient()
            body = f"[Atualização de proposta]\n\nPreço atualizado: {_fmt_brl(novo_preco)}"
            message_id = zc.send_text(args.phone, body)
            info_envio = {"reenviado": True, "message_id": message_id}
        except Exception as e:
            info_envio = {"reenviado": False, "erro": str(e)}

    _print_json({
        "proposta_id": args.proposta_id,
        "preco_antigo": _fmt_brl(preco_atual),
        "preco_novo": _fmt_brl(novo_preco),
        **info_envio
    })


def cmd_proposta_events(args):
    init_db()
    repo = PropostaRepository()
    evts = repo.eventos(args.proposta_id)
    _print_json(evts)


def cmd_proposta_list(args):
    init_db()
    repo = PropostaRepository()
    lst = repo.listar_por_cliente(args.cliente_id, status=args.status, limit=args.limit, offset=args.offset)
    _print_json(lst)


def cmd_proposta_accept(args):
    init_db()
    repo = PropostaRepository()
    repo.marcar_aceita(args.proposta_id)
    _print_json({"proposta_id": args.proposta_id, "status": "accepted"})


# -----------------------------------------------------------------------------
# Parsers / CLI
# -----------------------------------------------------------------------------
def _lazy(name: str):
    return lambda args: globals()[name](args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="meu_app", description="CLI App Jurídico – Etapas 1 e 2")

    sp = p.add_subparsers(dest="cmd")  # subcomando OPCIONAL

    # Índice
    sp_info = sp.add_parser("index-info", help="Mostra status do índice/manifest e diretórios envolvidos")
    sp_info.set_defaults(func=_lazy("cmd_index_info"))

    sp_rebuild = sp.add_parser("rebuild-index", help="Recria o índice do zero")
    sp_rebuild.set_defaults(func=_lazy("cmd_index_rebuild"))

    sp_update = sp.add_parser("update-index", help="Atualiza o índice incrementalmente (ou faz rebuild se necessário)")
    sp_update.set_defaults(func=_lazy("cmd_index_update"))

    # Atendimento
    sp_ask = sp.add_parser("ask", help="Faz uma pergunta única no fluxo de atendimento")
    sp_ask.add_argument("--nome", default="Cliente CLI")
    sp_ask.add_argument("--phone")
    sp_ask.add_argument("--pergunta", required=True)
    sp_ask.set_defaults(func=_lazy("cmd_ask"))

    sp_chat = sp.add_parser("chat", help="Abre um chat interativo no fluxo de atendimento")
    sp_chat.add_argument("--nome", default="Cliente CLI")
    sp_chat.add_argument("--phone")
    sp_chat.set_defaults(func=_lazy("cmd_chat"))

    # Webhooks Z-API
    sp_web = sp.add_parser("configure-webhooks", help="Configura webhooks da Z-API")
    sp_web.add_argument("--received-url")
    sp_web.add_argument("--delivery-url")
    sp_web.set_defaults(func=_lazy("cmd_configure_webhooks"))

    # Propostas
    sp_prev = sp.add_parser("preview-proposal", help="Gera texto e preço sugerido (sem enviar)")
    sp_prev.add_argument("--nome", required=True)
    sp_prev.add_argument("--resumo", required=True)
    sp_prev.add_argument("--valor", type=float, required=True, help="Valor econômico estimado (BRL)")
    sp_prev.set_defaults(func=_lazy("cmd_proposta_preview"))

    sp_send = sp.add_parser("send-proposal", help="Gera e envia uma proposta para o cliente (WhatsApp)")
    sp_send.add_argument("--phone", required=True)
    sp_send.add_argument("--nome", required=True)
    sp_send.add_argument("--resumo", required=True)
    sp_send.add_argument("--valor", type=float, required=True)
    sp_send.set_defaults(func=_lazy("cmd_proposta_send"))

    sp_disc = sp.add_parser("discount-proposal", help="Aplica desconto (respeitando arredondamento) e opcionalmente reenvia")
    sp_disc.add_argument("--proposta-id", required=True)
    sp_disc.add_argument("--resumo")
    sp_disc.add_argument("--valor", type=float, default=0.0, help="(Opcional) valor econômico para recomputar piso futuramente")
    g = sp_disc.add_mutually_exclusive_group(required=False)
    g.add_argument("--percent", type=float, default=0.0, help="Percentual de desconto (0-100)")
    g.add_argument("--target", type=float, help="Preço alvo em BRL (será arredondado)")
    sp_disc.add_argument("--resend", action="store_true")
    sp_disc.add_argument("--phone")
    sp_disc.set_defaults(func=_lazy("cmd_proposta_discount"))

    sp_evt = sp.add_parser("proposal-events", help="Mostra eventos de uma proposta")
    sp_evt.add_argument("--proposta-id", required=True)
    sp_evt.set_defaults(func=_lazy("cmd_proposta_events"))

    sp_list = sp.add_parser("list-proposals", help="Lista propostas por cliente")
    sp_list.add_argument("--cliente-id", required=True)
    sp_list.add_argument("--status")
    sp_list.add_argument("--limit", type=int, default=50)
    sp_list.add_argument("--offset", type=int, default=0)
    sp_list.set_defaults(func=_lazy("cmd_proposta_list"))

    sp_acc = sp.add_parser("accept-proposal", help="Marca aceite de uma proposta")
    sp_acc.add_argument("--proposta-id", required=True)
    sp_acc.set_defaults(func=_lazy("cmd_proposta_accept"))

    # Fallback: sem subcomando -> imprime help e retorna 0 (sem SystemExit:2)
    def _no_cmd(args, _p=p):
        _p.print_help()
        return 0
    p.set_defaults(func=_no_cmd)

    return p


def main(argv: Optional[List[str]] = None):
    # Garante que o schema esteja migrado antes de qualquer operação
    init_db()
    parser = build_parser()
    args = parser.parse_args(argv)
    ret = args.func(args)
    return 0 if ret is None else ret


if __name__ == "__main__":
    raise SystemExit(main())
