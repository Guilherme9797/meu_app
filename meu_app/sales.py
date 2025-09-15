from typing import Optional

def build_offer_text(area: str, subtype: str, budget_tone: Optional[str], deadline: Optional[str]) -> str:
    urg = f"Seu prazo de defesa é **{deadline}**." if deadline else "Seu prazo de defesa está correndo."
    ancoragem = "É um investimento pequeno para evitar multa alta e suspensão de 12 meses."
    if budget_tone == "apertado":
        ancoragem += " Eu adapto honorários com entrada acessível e parcelas."

    planos = [
        ("Essencial", "Defesa prévia completa + protocolo + acompanhamento do resultado", "R$ 490", "entrada + 2x"),
        ("Intermediário", "Defesa + Recurso JARI (2ª etapa) se necessário", "R$ 790", "entrada + 3x"),
        ("Completo", "Defesa + JARI + CETRAN com sustentação, se preciso", "R$ 1.290", "entrada + 4x"),
    ]
    bullets = "\n".join([f"• **{n}** — {desc} — **{preco}** ({parcelas})" for n,desc,preco,parcelas in planos])

    return (
        f"{urg}\n\n"
        "Plano de ação:\n"
        "1) Montamos defesa destacando ausência de oferta de exame alternativo e falhas de formalização;\n"
        "2) Protocolamos e acompanhamos; se necessário, já seguimos para recurso.\n\n"
        f"{ancoragem}\n\n"
        f"Opções de honorários:\n{bullets}"
    )