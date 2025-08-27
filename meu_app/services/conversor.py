from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

import os
import logging
import json
import math
import textwrap

try:
    from ..utils import OpenAIClient
except Exception:
    from meu_app.utils import OpenAIClient  # type: ignore

try:
    from .buscador_pdf import BuscadorPDF
except Exception:
    from meu_app.services.buscador_pdf import BuscadorPDF  # type: ignore

# PricingService oficial (sem fallback heurístico por padrão)
try:
    from .pricing import PricingService, PricingInput  # type: ignore
except Exception:
    # Fallback mínimo só para não quebrar em ambientes sem o arquivo.
    class PricingInput:
        def __init__(self, resumo: str, valor_economico_brl: Optional[float] = None):
            self.resumo = resumo
            self.valor_economico_brl = valor_economico_brl
    class _Preciso:
        def __init__(self, sugerido_brl: float, categoria: str = "heuristica"):
            self.sugerido_brl = sugerido_brl
            self.categoria = categoria
    class PricingService:
        def __init__(self, piso_min_brl: float = 1200.0):
            self.piso = piso_min_brl
        def sugerir(self, data: PricingInput) -> _Preciso:
            base = float(data.valor_economico_brl or 0.0)
            if base <= 0:
                return _Preciso(self.piso, "heuristica")
            # 8% arredondado em múltiplos de 5
            sug = max(self.piso, math.ceil((base * 0.08) / 5.0) * 5.0)
            return _Preciso(float(sug), "heuristica")

try:
    from ..persistence.repositories import PropostaRepository
except Exception:
    from meu_app.persistence.repositories import PropostaRepository  # type: ignore

log = logging.getLogger(__name__)

WHATSAPP_MAX_CHARS = int(os.getenv("PROPOSTA_WHATSAPP_MAX_CHARS", "4000"))
PARCELAS_MAX = int(os.getenv("PROPOSTA_PARCELAS_MAX", "3"))
COPY_VARIANT = os.getenv("PROPOSTA_COPY_VARIANT", "A").upper()
CTA_PAGAMENTO_LABEL = os.getenv("PROPOSTA_CTA_LABEL", 'Responda "ACEITO" para começar')
TONE = os.getenv("PROPOSTA_TONE", "amigavel").lower()
INCLUDE_OBJECTIONS = os.getenv("PROPOSTA_INCLUDE_OBJECTIONS", "1") in {"1", "true", "True"}
INCLUDE_GUARANTEE = os.getenv("PROPOSTA_INCLUDE_GUARANTEE", "1") in {"1", "true", "True"}
FOLLOWUP_SIGNATURE = os.getenv("PROPOSTA_SIGNATURE", "Equipe Jurídica")

@dataclass
class PropostaPreview:
    texto: str
    preco_centavos: int
    preco_reais: float
    categoria_interna: str

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
    f"- Pagamento: parcelamos em até {{parcelas_max}}x no cartão.\n"
    "- Acompanhamento: você recebe atualizações a cada etapa."
)

GARANTIA_TEXTO = "Compromisso: comunicação clara, alinhamento prévio de cada passo e foco na solução mais rápida e segura para você."

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
        txt = txt.replace("Olá", "Prezado(a)")
        txt = txt.replace("Podemos seguir agora?", "Podemos prosseguir?")
        txt = txt.replace("Por que conosco:", "Diferenciais:")
    return txt

class ConversorPropostas:
    def __init__(self, openai_client: OpenAIClient, buscador: BuscadorPDF):
        self.oai = openai_client
        self.buscador = buscador
        self.repo = PropostaRepository()
        self.pricing = PricingService()

    def _estimar_preco(self, resumo: str, valor_economico_brl: Optional[float]):
        """
        Encapsula a precificação via PricingService.
        Retorna o objeto do PricingService (com .sugerido_brl e .categoria).
        """
        return self.pricing.sugerir(PricingInput(resumo=resumo, valor_economico_brl=valor_economico_brl))

    def _refinar_estrategia_passos(self, nome: str, resumo: str, contexto: str) -> Dict[str, Any]:
        estrategia = "Iniciar com análise documental e tentativa de solução extrajudicial."
        passos_list: List[str] = ["Analisar documentos", "Definir estratégia", "Peticionar ou negociar com a parte contrária"]
        try:
            system = (
                "Você é um consultor jurídico que escreve propostas claras, objetivas e persuasivas, "
                "sem juridiquês e com foco em benefícios práticos. Não cite fontes internas nem tabelas. "
                "Responda **apenas** um JSON."
            )
            user = (
                f"Cliente: {nome}\nResumo do problema: {resumo}\n"
                f"Contexto (se houver):\n{(contexto or '(sem base interna)')}\n\n"
                "Gere JSON com as chaves exatas: "
                '{"estrategia": string (1-2 frases objetivas), "passos": lista de 3 a 6 itens (frases curtas)}. '
                "Escreva em português do Brasil."
            )
            out = self.oai.chat(system=system, user=user)
            data_txt = (out or "").strip()
            data: Dict[str, Any] = {}
            try:
                data = json.loads(data_txt)
            except Exception:
                import re
                m = re.search(r"\{[\s\S]*\}", data_txt)
                if m:
                    try:
                        data = json.loads(m.group(0))
                    except Exception:
                        data = {}
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

    def _gerar_texto(self, nome: str, resumo: str, contexto: str, preco_reais: float) -> str:
        refinado = self._refinar_estrategia_passos(nome, resumo, contexto)
        return self._montar_template(nome, resumo, refinado["estrategia"], refinado["passos"], preco_reais)

    def preview(self, nome: str, resumo_problema: str, valor_economico_brl: Optional[float] = None) -> PropostaPreview:
        contexto = self.buscador.buscar_contexto(resumo_problema)
        prec = self._estimar_preco(resumo_problema, valor_economico_brl)
        texto = self._gerar_texto(nome, resumo_problema, contexto, preco_reais=prec.sugerido_brl)
        return PropostaPreview(
            texto=texto,
            preco_centavos=int(round(prec.sugerido_brl * 100)),
            preco_reais=prec.sugerido_brl,
            categoria_interna=getattr(prec, "categoria", "default"),
        )

    def criar_e_enviar(self, cliente_id: str, nome: str, phone: str, resumo_problema: str, valor_economico_brl: Optional[float] = None) -> Dict[str, Any]:
        contexto = self.buscador.buscar_contexto(resumo_problema)
        prec = self._estimar_preco(resumo_problema, valor_economico_brl)
        preco_cent = int(round(prec.sugerido_brl * 100))
        texto = self._gerar_texto(nome, resumo_problema, contexto, preco_reais=prec.sugerido_brl)
        prop_id = self.repo.criar_draft(cliente_id=cliente_id, texto=texto, preco_centavos=preco_cent, moeda="BRL", canal="whatsapp")
        message_id = None
        sent = False
        err = None
        try:
            from .zapi_client import ZapiClient
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
            "categoria_interna": getattr(prec, "categoria", "default"),
            "erro_envio": err,
        }

    def revisar_e_atualizar(self, proposta_id: str, nome: str, resumo_problema: str, novo_preco_reais: float) -> Dict[str, Any]:
        contexto = self.buscador.buscar_contexto(resumo_problema)
        texto = self._gerar_texto(nome, resumo_problema, contexto, preco_reais=novo_preco_reais)
        self.repo.atualizar_texto_preco(proposta_id, texto=texto, preco_centavos=int(round(novo_preco_reais * 100)))
        return {"proposta_id": proposta_id, "preco_reais": round(novo_preco_reais, 2)}

    def reenviar(self, proposta_id: str, phone: str, prefixo: Optional[str] = None) -> Dict[str, Any]:
        from .zapi_client import ZapiClient
        row = self.repo.obter(proposta_id)
        if not row:
            raise ValueError("Proposta não encontrada")
        texto = row["texto"]
        cab = (prefixo + "\n\n") if prefixo else ""
        msg = f"{cab}{texto}\n\nID da proposta: {proposta_id}"
        zc = ZapiClient()
        resp = zc.send_text(phone, msg)
        mid = (resp or {}).get("messageId") or (resp or {}).get("id")
        self.repo.marcar_enviada(proposta_id, message_id=mid)
        return {"status": "sent", "message_id": mid}

    def followup_copy(self, nome: str, proposta_id: str, curtinha: bool = True) -> str:
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
        base = textwrap.shorten(" ".join(texto_proposta.split()), width=max_chars, placeholder="...")
        return _truncate(base, max_chars)
