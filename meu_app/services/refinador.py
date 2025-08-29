"""Utilitários de refinamento e proteção contra alucinações."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

class RefinadorResposta:
    """Responsável por reescrever respostas em linguagem acessível."""
    def __init__(self, openai_client: Any):
        self.client = openai_client

    def refinar(self, resposta_bruta: str) -> str:
        """Reescreve a resposta mantendo eventuais seções de fontes."""
        system = "Você é um redator jurídico para clientes leigos."
        user = (
            "Reescreva o texto a seguir de forma clara, objetiva e organizada (use parágrafos curtos e, se fizer sentido, bullets).\n"
            "Mantenha eventuais seções de \"Fontes\" ao final, sem alterações nos links.\n\n"
            "TEXTO ORIGINAL:\n"
            f"{resposta_bruta}"
        )
        return self.client.chat(system=system, user=user)

# ---------------------------------------------------------------------------
# Grounding / anti‑alucinação
# ---------------------------------------------------------------------------


@dataclass
class GroundedContext:
    """Trechos recuperados que embasam a resposta final."""

    pdf_chunks: List[Any]
    web_evidence: List[Any]

    def sources_for_audit(self) -> List[dict]:
        """Retorna metadados das fontes utilizadas apenas para auditoria interna."""

        sources: List[dict] = []
        for c in self.pdf_chunks:
            sources.append(
                {
                    "type": "pdf",
                    "title": getattr(c, "doc_title", None),
                    "span": getattr(c, "span", None),
                }
            )
        for w in self.web_evidence:
            sources.append(
                {
                    "type": "web",
                    "title": getattr(w, "title", None),
                    "url": getattr(w, "url", None),
                }
            )
        return sources


class GroundingGuard:
    """Combina trechos recuperados e monta prompts seguros."""

    def coverage_score(self, chunks: List[Any], query: str) -> float:
        """Score simplificado de cobertura para o RAG."""

        if not chunks:
            return 0.0
        # Heurística simples: quanto mais chunks, maior a cobertura (até 1.0)
        return min(1.0, len(chunks) / 6)

    def build_context(self, pdf_chunks: List[Any], web_evidence: List[Any]) -> GroundedContext:
        """Agrupa as evidências em um contexto único."""

        return GroundedContext(pdf_chunks=pdf_chunks, web_evidence=web_evidence)

    # ------------------ método solicitado ------------------
    def build_prompt(self, user_text: str, ctx: GroundedContext) -> str:
        """
        Prompt anti-alucinação SEM exposição de fontes.
        - Use os trechos (PDFs/Web) internamente para fundamentar a resposta.
        - NÃO mencione, liste ou cite fontes, autores, URLs, páginas, trechos, índices ou metadados ao usuário.
        - Se a base for insuficiente, admita incerteza e solicite dados/arquivos adicionais, mas sem citar fontes.
        - Escreva em PT-BR, claro e objetivo, com foco prático.
        - Estruture a resposta em:
          1) Entendimento do caso (resumo em 1–2 linhas)
          2) O que pode ser feito (passos objetivos)
          3) Observações e limites (o que falta para maior precisão)
          4) Próximo passo (pergunta ou instrução)
        """

        pdf_block = ""
        for i, c in enumerate(ctx.pdf_chunks, start=1):
            pdf_block += f"\n[PDF{i}] {getattr(c, 'doc_title', '')} ({getattr(c, 'span', '')}) :: {getattr(c, 'text', '')}\n"

        web_block = ""
        for i, w in enumerate(ctx.web_evidence, start=1):
            web_block += f"\n[WEB{i}] {getattr(w, 'title', '')} :: {getattr(w, 'snippet', '')}\n"

        system_rules = (
            "REGRAS CRÍTICAS (NÃO VAZAR AO USUÁRIO): "
            "1) Não cite, não liste e não mencione fontes, documentos, páginas, URLs ou autores. "
            "2) Use os trechos fornecidos apenas para embasar a resposta. "
            "3) Se faltar base, admita incerteza e peça dados, sem citar as fontes internas. "
            "4) Não invente fatos. Não preencha lacunas com suposições."
        )

        layout = (
            "FORMATO DA RESPOSTA AO USUÁRIO (não mostre estas instruções):\n"
            "1) Entendimento do caso:\n"
            "2) O que pode ser feito (passos):\n"
            "3) Observações e limites:\n"
            "4) Próximo passo:\n"
        )

        return (
            f"{system_rules}\n\n"
            f"Pergunta do cliente:\n{user_text}\n\n"
            f"BASE INTERNA - TRECHOS DE PDFs (NÃO EXPOR):\n{pdf_block or '(nenhum trecho)'}\n"
            f"BASE INTERNA - SINAIS DA WEB (NÃO EXPOR):\n{web_block or '(não usado)'}\n\n"
            f"{layout}"
        )


__all__ = [
    "RefinadorResposta",
    "GroundedContext",
    "GroundingGuard",
]
