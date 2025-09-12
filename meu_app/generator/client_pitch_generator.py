# -*- coding: utf-8 -*-
"""Gerador de respostas comerciais curtas com CTA."""

from __future__ import annotations

import logging
from textwrap import dedent
from typing import Any, Dict, Optional

DEFAULT_BRANDING = {
    "firm_name": "Seu Escritório de Advocacia",
    "cta_phone": "(11) 99999-0000",
    "cta_whatsapp": "https://wa.me/55999990000",
    "cta_email": "contato@seuescritorio.com.br",
    "cta_city": "atuação nacional",
}

SALES_SYSTEM_PROMPT = dedent(
    """
    Você é um advogado brasileiro especialista. Escreva em linguagem simples, humana e acolhedora.
    Objetivo: ajudar de forma prática e convidar o cliente a nos contatar.
    Regras:
    - Foque nas providências e caminhos legais (sem jargão excessivo).
    - Não invente fatos. Se faltar dado essencial, peça até 3 informações objetivas no final.
    - Use estrutura clara: diagnóstico, o que dá para fazer, documentos, prazos/risco, próximos passos, convite para contato.
    - Seja cordial, direto e positivo — sem prometer resultado.
    """
).strip()


def render_sales_user_prompt(pergunta_do_cliente: str) -> str:
    return dedent(
        f"""
        Pergunta do cliente (texto literal):
        ---
        {pergunta_do_cliente.strip()}
        ---

        Redija a resposta como um advogado brasileiro especialista, de forma simples e carismática.
        Traga soluções práticas e caminho processual/administrativo possível.
        Explique vantagens de nos contratar (organização do caso, estratégia, agilidade, acompanhamento).
        No final, inclua um convite claro para contato.

        Formato sugerido:
        1) Diagnóstico resumido
        2) O que dá para fazer agora (passo a passo)
        3) Documentos essenciais
        4) Prazos e riscos
        5) Próximos passos + CTA (contato)
        """
    ).strip()


def _extract_text(resp: Any) -> str:
    """Normaliza a saída entre Chat Completions e Completions."""

    try:  # objetos estilo openai
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        pass
    try:
        return (resp.choices[0].text or "").strip()
    except Exception:
        pass
    try:  # dicts aninhados
        ch0 = resp.get("choices", [{}])[0]
        return (ch0.get("message", {}).get("content") or ch0.get("text") or "").strip()
    except Exception:
        pass
    return ""


class ClientPitchGenerator:
     """Gera respostas comerciais universais com CTA."""

     def __init__(
        self,
        llm: Any,
        logger: Optional[logging.Logger] = None,
        branding: Optional[Dict[str, str]] = None,
    ) -> None:
        self.llm = llm
        self.logger = logger or logging.getLogger(__name__)
        self.branding = {**DEFAULT_BRANDING, **(branding or {})}
        self.contact_block = (
            "Entre em contato agora:\n"
            f"• Telefone: {self.branding['cta_phone']}\n"
            f"• WhatsApp: {self.branding['cta_whatsapp']}\n"
            f"• E-mail: {self.branding['cta_email']}\n"
            f"• Atendimento: {self.branding['cta_city']}"
        )
    
     def compose(
        self, user_utterance: str, extra_context: Optional[Dict[str, Any]] = None
    ) -> str:
        sys_prompt = SALES_SYSTEM_PROMPT
        user_prompt = render_sales_user_prompt(user_utterance)
        if self.logger:
            self.logger.info(
                "ClientPitchGenerator: enviando prompt comercial direto ao LLM."
            )

        try:
            resp = self.llm.chat(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.35,
                max_tokens=900,
                extra_body={"top_k": 40},
            )
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    "Falha no chat (com temperature); tentando sem parâmetros sensíveis: %s",
                    e,
                )
            resp = self.llm.chat(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
        text = _extract_text(resp)

        if not text or len(text) < 80:
            if self.logger:
                self.logger.warning(
                    "Saída curta/genérica; reforçando prompt e reintentando."
                )
            user_prompt2 = (
                user_prompt
                + "\n\nReforce o plano com medidas concretas e finalize com um convite para falar com nosso time."
            )
            resp2 = self.llm.chat(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt2},
                ]
            )
            text2 = _extract_text(resp2)
            text = text2 or text

        if "WhatsApp" not in text and "whatsapp" not in text and "contato@" not in text:
            text = text.rstrip() + "\n\n" + self.contact_block

        text = f"{self.branding['firm_name']}\n\n{text}"
        return text
