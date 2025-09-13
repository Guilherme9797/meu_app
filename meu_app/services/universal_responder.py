from typing import List, Dict, Any
from pathlib import Path
from meu_app.utils.openai_client import LLM

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
REALIZER_SYS = (PROMPTS_DIR / "whatsapp_system_universal.txt").read_text(encoding="utf-8")

REALIZER_USER_TMPL = """Preencha as 4 bolhas a partir destes slots:

user_problem: {user_problem}
risk_benefit: {risk_benefit}
low_friction_step: {low_friction_step}
escalation_step: {escalation_step}
triage_questions: {triage_questions}
social_proof: {social_proof}
docs_to_request: {docs_to_request}
price_anchor: {price_anchor}

REGRAS:
- 3 a 4 bolhas, até 4 linhas cada.
- WhatsApp friendly, direto e humano.
- Última bolha: CTA binário + 3 perguntas (use triage_questions).
- Se social_proof não for vazio, use 1 linha curta após a empatia.
- Não prometa resultado. Não dar aula.
- Não use marcadores longos; mantenha frases curtas.

Entregue APENAS as bolhas separadas por: <BUBBLE> ... </BUBBLE>.
"""

def realize(llm: LLM, slots: Dict[str, Any]) -> List[str]:
    msg = REALIZER_USER_TMPL.format(**slots)
    messages = [
        {"role": "system", "content": REALIZER_SYS},
        {"role": "user", "content": msg},
    ]
    out = llm.chat(messages, temperature=0.4, presence_penalty=0.3, top_p=0.9)
    # split em bolhas
    bubbles: List[str] = []
    cur: List[str] = []
    for line in out.splitlines():
        if "<BUBBLE>" in line:
            cur = []
        elif "</BUBBLE>" in line:
            text = "\n".join([l for l in cur if l.strip()])[:700]
            if text:
                bubbles.append(text)
        else:
            cur.append(line)
    # fallback: se o modelo não respeitar tags, cria 3 bolhas padrão
    if not bubbles:
        tri = slots.get("triage_questions", [])
        tri_fmt = " ".join([f"{i+1}) {q}" for i, q in enumerate(tri[:3])])
        bubbles = [
            "Entendi. Isso acontece e tem solução.",
            slots["risk_benefit"],
            f"Passo a passo: {slots['low_friction_step']} → {slots['escalation_step']}.",
            f"Quer que eu olhe seus documentos e te diga o melhor caminho? Responde: {tri_fmt}",
        ]
    return bubbles[:4]