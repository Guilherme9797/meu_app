from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

import os
import logging
import json
import math
import textwrap

# Imports robustos (relativo + fallback absoluto)
try:
    from ..utils import OpenAIClient
except Exception:
    from meu_app.utils import OpenAIClient  # type: ignore

try:
    from .buscador_pdf import BuscadorPDF
except Exception:
    from meu_app.services.buscador_pdf import BuscadorPDF  # type: ignore

# Pricing pode não existir no ambiente — definimos fallback seguro
try:
    from .pricing import PricingService, PricingInput  # type: ignore
except Exception:
    class PricingInput:
        def __init__(self, resumo: str, valor_economico_brl: Optional[float] = None):
            self.resumo = resumo
            self.valor_economico_brl = valor_economico_brl

    class _Preciso:
        def __init__(self, sugerido_brl: float, categoria: str = "default"):
            self.sugerido_brl = sugerido_brl
            self.categoria = categoria

    class PricingService:
        def __init__(self, piso_min_brl: float = 300.0):
            self.piso = piso_min_brl

        def sugerir(self, data: PricingInput) -> _Preciso:
            base = float(data.valor_economico_brl or 0.0)
            if base <= 0:
                return _Preciso(self.piso, "piso")
            # heurística simples: 6% do valor econômico, limitado por piso
            sugerido = max(self.piso, round(base * 0.06 / 5) * 5)
            return _Preciso(float(sugerido), "heuristica")

try:
    from ..persistence.repositories import PropostaRepository
except Exception:
    from meu_app.persistence.repositories import PropostaRepository  # type: ignore

log = logging.getLogger(__name__)

# -------------------------- Config via ambiente --------------------------
WHATSAPP_MAX_CHARS = int(os.getenv("PROPOSTA_WHATSAPP_MAX_CHARS", "4000"))
PARCELAS_MAX = int(os.getenv("PROPOSTA_PARCELAS_MAX", "3"))
COPY_VARIANT = os.getenv("PROPOSTA_COPY_VARIANT", "A").upper()  # "A" ou "B"
CTA_PAGAMENTO_LABEL = os.getenv("PROPOSTA_CTA_LABEL", 'Responda "ACEITO" para começar')
TONE = os.getenv("PROPOSTA_TONE", "amigavel").lower()  # amigavel|formal
INCLUDE_OBJECTIONS = os.getenv("PROPOSTA_INCLUDE_OBJECTIONS", "1") in {"1", "true", "True"}
INCLUDE_GUARANTEE = os.getenv("PROPOSTA_INCLUDE_GUARANTEE", "1") in {"1", "true", "True"}
FOLLOWUP_SIGNATURE = os.getenv("PROPOSTA_SIGNATURE", "Equipe Jurídica")

# ------------------------------------------------------------------------

@dataclass
class PropostaPreview:
    texto: str
    preco_centavos: int
    preco_reais: float
    categoria_interna: str  # uso interno (não exibir ao cliente)

# ------------------------------ Templates ------------------------------
TEMPLATE_A = """
Proposta de Atendimento Jurídico

Olá, {nome_cliente}! Analisei sua situação: {resumo_problema}.

Como podemos ajudar:
1) Avaliação detalhada do seu caso com base em documentos e jurisprudência;
2) Estratégia recomendada: {estrategia};
3) Próximos passos: {passos}.

Honorários:
- Valor fixo: {preco_formatado} (inclui análise inicial e petição/negociação).
- Condições: parcelamento em até {parcelas_max}x sem juros no cartão ou 1x via PIX.

{diferenciais}

{objeções}

Se estiver de acordo, {cta}.
"""

TEMPLATE_B = """
Plano de Ação & Honorários

{nome_cliente}, resumindo seu caso: {resumo_problema}.

Estratégia:
{estrategia}

Passos imediatos:
- {passos_bullet}

Honorários e condições:
- {preco_formatado} (fixo, cobre análise inicial + redação/negociação);
- Parcelamento: até {parcelas_max}x no cartão ou 1x no PIX.

{diferenciais}

{objeções}

Podemos seguir agora? {cta}.
"""

# blocos opcionais
DIFERENCIAIS_AMIGAVEL = (
    "Por que conosco:\n"
    "- Linguagem simples e comunicação transparente;\n"
    "- Experiência em casos semelhantes;\n"
    "- Acompanhamento próximo em cada etapa."
)
DIFERENCIAIS_FORMAL = (
    "Diferenciais:\n"
    "- Atendimento objetivo e transparente;\n"
    "- Atuação em casos análogos;\n"
    "- Controle de prazos e atualização de cada fase."
)

OBJECOES_CURTAS = (
    "Dúvidas comuns:\n"
    "- Prazo: iniciamos assim que recebermos seus documentos.\n"
    "- Pagamento: parcelamos em até {parcelas_max}x no cartão.\n"
    "- Acompanhamento: você recebe atualizações a cada etapa."
)

GARANTIA_TEXTO = "Compromisso: comunicação clara, alinhamento prévio de cada passo e foco na solução mais rápida e segura para você."

# -------------------------- Utilidades de texto --------------------------
def _fmt_brl(x: float) -> str:
    inteiro = int(math.floor(x))
    cent = int(round((x - inteiro) * 100))
    s = f"{inteiro:,}".replace(",", ".")
    return f"R$ {s},{cent:02d}"

def _truncate(s: str, max_len: int) -> str:
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3].rstrip() + "..."

def _tone_wrap(txt: str) -> str:
    if TONE == "formal":
        # ajustes leves de tom
        txt = txt.replace("Olá", "Prezado(a)")
        txt = txt.replace("Podemos seguir agora?", "Podemos prosseguir?")
        txt = txt.replace("Por que conosco:", "Diferenciais:")
    return txt

# -------------------------- Classe principal -----------------------------
class ConversorPropostas:
    """
    - Gera proposta (texto) a partir do resumo do problema + contexto dos PDFs.
    - Calcula preço com PricingService (piso mínimo + markup + arredondamento),
      garantindo valor > mínimo e sem nunca expor a fonte.
    - Persiste como draft e envia via Z-API (marcando 'sent').
    - Auxiliares: preview, revisar_e_atualizar, reenviar, followups.
    """

    def __init__(self, openai_client: OpenAIClient, buscador: BuscadorPDF):
        self.oai = openai_client
        self.buscador = buscador
        self.repo = PropostaRepository()
        self.pricing = PricingService()

    # ------------------------- Geração com OpenAI -------------------------

    def _refinar_estrategia_passos(self, nome: str, resumo: str, contexto: str) -> Dict[str, Any]:
        """Pede um JSON {estrategia:str, passos:list[str]}. Usa fallback seguro."""
        estrategia = "Iniciar com análise documental e tentativa de solução extrajudicial."
        passos_list: List[str] = ["Analisar documentos", "Definir estratégia", "Peticionar ou negociar com a parte contrária"]

        try:
            msgs = [
                {
                    "role": "system",
                    "content": (
                        "Você é um consultor jurídico que escreve propostas claras, objetivas e persuasivas, "
                        "sem juridiquês e com foco em benefícios práticos. Não cite fontes internas nem tabelas."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Cliente: {nome}\nResumo do problema: {resumo}\n"
                        f"Contexto (se houver):\n{(contexto or '(sem base interna)')}\n\n"
                        "Gere JSON com: estrategia (1-2 frases objetivas) e passos (lista curta de 3 a 6 itens, frases curtas). "
                        "Escreva em português do Brasil, tom claro e acessível."
                    ),
                },
            ]
            out = self.oai.chat(msgs)
            data = json.loads(out) if out else {}
            if isinstance(data, dict):
                e = (data.get("estrategia") or "").strip()
                if e:
                    estrategia = e
                p = data.get("passos")
                if isinstance(p, list) and p:
                    passos_list = [str(i).strip() for i in p if str(i).strip()][:6]
        except Exception as e:
            logging.getLogger(__name__).warning("Conversor: falha ao refinar estrategia/passos (%s). Usando fallback.", e)

        return {"estrategia": estrategia, "passos": passos_list}

    def _blocos_opcionais(self) -> Dict[str, str]:
        dif = DIFERENCIAIS_AMIGAVEL if TONE == "amigavel" else DIFERENCIAIS_FORMAL
        obj = (OBJECOES_CURTAS.format(parcelas_max=PARCELAS_MAX) if INCLUDE_OBJECTIONS else "").strip()
        gar = (GARANTIA_TEXTO if INCLUDE_GUARANTEE else "").strip()
        bloco = dif
        if gar:
            bloco = f"{bloco}\n- {gar}" if TONE == "amigavel" else f"{bloco}\n{gar}"
        return {"diferenciais": bloco, "objeções": obj}

    def _montar_template(self, nome: str, resumo: str, estrategia: str, passos: List[str], preco_brl: float) -> str:
        preco_fmt = _fmt_brl(preco_brl)
        cta = CTA_PAGAMENTO_LABEL
        blocos = self._blocos_opcionais()

        if COPY_VARIANT == "B":
            passos_bullet = "\n- ".join([p for p in passos]) if passos else "Definir próximos passos em chamada breve"
            txt = TEMPLATE_B.format(
                nome_cliente=nome,
                resumo_problema=resumo,
                estrategia=estrategia,
                passos_bullet=passos_bullet,
                preco_formatado=preco_fmt,
                parcelas_max=PARCELAS_MAX,
                cta=cta,
                diferenciais=blocos["diferenciais"],
                objeções=blocos["objeções"] or "",
            )
        else:
            passos_str = "; ".join(passos) if passos else "Analisar documentos; Definir estratégia; Peticionar/Negociar"
            txt = TEMPLATE_A.format(
                nome_cliente=nome,
                resumo_problema=resumo,
                estrategia=estrategia,
                passos=passos_str,
                preco_formatado=preco_fmt,
                parcelas_max=PARCELAS_MAX,
                cta=cta,
                diferenciais=blocos["diferenciais"],
                objeções=blocos["objeções"] or "",
            )

        txt = _tone_wrap(txt)
        return _truncate(txt, WHATSAPP_MAX_CHARS)

    # ---------------------------- API “privada” ----------------------------
    def _gerar_texto(self, nome: str, resumo: str, contexto: str, preco_reais: float) -> str:
        refinado = self._refinar_estrategia_passos(nome, resumo, contexto)
        return self._montar_template(nome, resumo, refinado["estrategia"], refinado["passos"], preco_reais)

    # ----------------------------- API pública -----------------------------

    def preview(self, nome: str, resumo_problema: str, valor_economico_brl: Optional[float] = None) -> PropostaPreview:
        """Calcula preço sugerido (> piso) e monta o texto (sem persistir/enviar)."""
        contexto = self.buscador.buscar_contexto(resumo_problema)
        prec = self.pricing.sugerir(PricingInput(resumo=resumo_problema, valor_economico_brl=valor_economico_brl))
        texto = self._gerar_texto(nome, resumo_problema, contexto, preco_reais=prec.sugerido_brl)
        return PropostaPreview(
            texto=texto,
            preco_centavos=int(round(prec.sugerido_brl * 100)),
            preco_reais=prec.sugerido_brl,
            categoria_interna=prec.categoria,
        )

    def criar_e_enviar(
        self,
        cliente_id: str,
        nome: str,
        phone: str,
        resumo_problema: str,
        valor_economico_brl: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Cria draft, envia via WhatsApp e marca como 'sent'."""
        # 1) contexto → reforça a proposta
        contexto = self.buscador.buscar_contexto(resumo_problema)

        # 2) preço sugerido (sempre > mínimo e arredondado)
        prec = self.pricing.sugerir(PricingInput(resumo=resumo_problema, valor_economico_brl=valor_economico_brl))
        preco_cent = int(round(prec.sugerido_brl * 100))

        # 3) texto (sem expor fontes internas)
        texto = self._gerar_texto(nome, resumo_problema, contexto, preco_reais=prec.sugerido_brl)

        # 4) persistir como draft
        prop_id = self.repo.criar_draft(
            cliente_id=cliente_id,
            texto=texto,
            preco_centavos=preco_cent,
            moeda="BRL",
            canal="whatsapp",
        )

        # 5) envio via WhatsApp (Z-API)
        message_id = None
        sent = False
        err = None
        try:
            from .zapi_client import ZapiClient  # import local para evitar ciclos
            zc = ZapiClient()
            msg = f"{texto}\n\nID da proposta: {prop_id}"
            resp = zc.send_text(phone, msg)
            message_id = (resp or {}).get("messageId") or (resp or {}).get("id")
            self.repo.marcar_enviada(prop_id, message_id=message_id)
            sent = True
        except Exception as e:
            log.exception("Conversor: falha ao enviar proposta %s para %s: %s", prop_id, phone, e)
            err = str(e)

        return {
            "proposta_id": prop_id,
            "enviada": sent,
            "message_id": message_id,
            "preco_centavos": preco_cent,
            "preco_reais": round(preco_cent / 100.0, 2),
            "categoria_interna": prec.categoria,  # útil em dashboards internos
            "erro_envio": err,
        }

    def revisar_e_atualizar(
        self,
        proposta_id: str,
        nome: str,
        resumo_problema: str,
        novo_preco_reais: float,
    ) -> Dict[str, Any]:
        """Gera novo texto coerente com o novo preço e atualiza a proposta (sem enviar)."""
        contexto = self.buscador.buscar_contexto(resumo_problema)
        texto = self._gerar_texto(nome, resumo_problema, contexto, preco_reais=novo_preco_reais)
        self.repo.atualizar_texto_preco(proposta_id, texto=texto, preco_centavos=int(round(novo_preco_reais * 100)))
        return {"proposta_id": proposta_id, "preco_reais": round(novo_preco_reais, 2)}

    def reenviar(self, proposta_id: str, phone: str, prefixo: Optional[str] = None) -> Dict[str, Any]:
        """Reenvia a proposta atual via WhatsApp e marca 'sent'."""
        from .zapi_client import ZapiClient

        row = self.repo.obter(proposta_id)
        if not row:
            raise ValueError("Proposta não encontrada")

        texto = row["texto"]
        msg = f"{(prefixo + '\n\n') if prefixo else ''}{texto}\n\nID da proposta: {proposta_id}"
        zc = ZapiClient()
        resp = zc.send_text(phone, msg)
        mid = (resp or {}).get("messageId") or (resp or {}).get("id")
        self.repo.marcar_enviada(proposta_id, message_id=mid)
        return {"status": "sent", "message_id": mid}

    # ----------------------- Extras úteis para conversão --------------------

    def followup_copy(self, nome: str, proposta_id: str, curtinha: bool = True) -> str:
        """Mensagem curta de follow-up para WhatsApp."""
        if curtinha:
            txt = (
                f"{nome}, tudo bem? Fiquei à disposição para avançarmos conforme a proposta ref. {proposta_id}. "
                f"Se estiver de acordo, {CTA_PAGAMENTO_LABEL.lower()}."
            )
        else:
            corpo = (
                "Podemos iniciar hoje mesmo. O processo começa com a análise dos seus documentos e o envio da primeira peça.\n"
                "Se preferir, me diga o melhor horário para uma chamada rápida de alinhamento."
            )
            txt = f"{nome}, seguindo sobre a proposta ref. {proposta_id}:\n{corpo}\n\n{CTA_PAGAMENTO_LABEL}."
        return _truncate(_tone_wrap(txt), min(600, WHATSAPP_MAX_CHARS))

    def resumo_curto(self, texto_proposta: str, max_chars: int = 700) -> str:
        """Cria um resumo enxuto da proposta para testes A/B em WhatsApp."""
        base = textwrap.shorten(" ".join(texto_proposta.split()), width=max_chars, placeholder="...")
        return _truncate(base, max_chars)
