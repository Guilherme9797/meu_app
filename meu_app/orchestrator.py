import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .storage import load_case, save_case
from .sales import build_offer_text

HOURS_FOR_RECAP = 72  # após 72h, sempre recapitula

@dataclass
class CaseFrame:
    phone: str
    area: str = ""          # ex: "trânsito"
    subtype: str = ""       # ex: "recusa 165-A"
    stage: str = "triage"   # triage|collect|offer|closing
    slots: Dict[str, str] = field(default_factory=dict)       # respostas
    asked: Dict[str, str] = field(default_factory=dict)       # slot->pergunta feita
    answered: List[str] = field(default_factory=list)         # slots respondidos
    budget_tone: Optional[str] = None                         # "apertado", etc.
    deadline: Optional[str] = None                            # data/prazo útil
    last_user_at: Optional[str] = None                        # ISO str
    last_bot_at: Optional[str] = None                         # ISO str
    buy_signal: bool = False
    value_drop_done: bool = False

    def now(self) -> datetime:
        return datetime.utcnow()

    def needs_recap(self) -> bool:
        if not self.last_user_at:
            return False
        last = datetime.fromisoformat(self.last_user_at)
        return (self.now() - last) > timedelta(hours=HOURS_FOR_RECAP)

logger = logging.getLogger(__name__)


CASE_REQUIRED_SLOTS = {
    # exemplo para CTB 165-A
    ("trânsito", "recusa 165-A"): [
        "prazo_defesa",
        "assinou_ciencia",
        "oferta_exame_alternativo",
    ]
}


QUESTION_TEXTS = {
    "data_notificacao": "Qual a data da ciência da notificação (dd/mm/aaaa)?",
    "prazo_defesa": "Confirma qual data limite aparece para a defesa?",
    "auto_enquadramento": "O auto menciona 165-A (recusa) exatamente?",
    "oferta_exame_alternativo": "Chegaram a oferecer exame de sangue ou outro teste? Foi por escrito ou só verbal?",
    "assinou_ciencia": "Você apenas assinou o campo de ciência no AIT, certo?",
    "provas_fotos": "Você tem fotos do auto e da sinalização? Pode enviar aqui?",
    "provas_video": "Tem vídeo da abordagem? Se sim, pode anexar?",
    "testemunhas": "Há testemunhas que presenciaram a abordagem? Quantas?",
}


MISSING_DESCRIPTIONS = {
    "prazo_defesa": "confirmar a data-limite",
    "assinou_ciencia": "confirmar se assinou só o campo de ciência",
    "oferta_exame_alternativo": "me dizer se ofereceram exame alternativo",
    "data_notificacao": "confirmar a data da notificação",
    "auto_enquadramento": "confirmar o enquadramento exato",
    "provas_fotos": "enviar as fotos",
    "provas_video": "enviar o vídeo",
    "testemunhas": "contar quem testemunhou",
}

def detect_case(text: str, case: CaseFrame) -> None:
    t = text.lower()
    if any(k in t for k in ["165-a", "bafômetro", "etilômetro", "recusa"]):
        case.area = "trânsito"
        case.subtype = "recusa 165-A"

def extract_slots(text: str) -> Dict[str, str]:
    import re
    t = text.lower()
    out: Dict[str, str] = {}

    if re.search(r"\\bassinei\\b.*ci[eê]n[cç]ia", t):
        out["assinou_ciencia"] = "sim"
    if re.search(r"\b(n[aã]o\s+(foi\s+)?ofere(c|ç)ido|n[aã]o\s+ofereceram|sem\s+oferta|sem\s+exame\s+alternativo)\b", t):
        out["oferta_exame_alternativo"] = "não"
    elif re.search(r"\b(ofereceram|foi\s+ofere(c|ç)ido)\b.*(sangue|exame)", t):
        out["oferta_exame_alternativo"] = "sim"

    if re.search(r"\b(v[ií]deo|video)\b", t):
        out["provas_video"] = "sim"
    if re.search(r"\bfoto(s)?\b", t):
        out["provas_fotos"] = "sim"
    if re.search(r"testemunh", t):
        out["testemunhas"] = "sim"
    m = re.search(r"at[eé]\s+(\d{2}/\d{2}/\d{4})", t)
    if m:
        out["prazo_defesa"] = m.group(1)
    m2 = re.search(r"recebi\s+a?\s*notifica[cç][aã]o.*?(\d{2}/\d{2}/\d{4})", t)
    if m2:
        out["data_notificacao"] = m2.group(1)
    
    if any(k in t for k in ["apertado", "parcel", "mais barato", "caminho mais barato"]):
        out["_budget_tone"] = "apertado"
    if any(k in t for k in ["preço", "preco", "valor", "honorár", "honorar", "quanto custa", "parcel"]):
        out["_buy_signal"] = "1"

    return out

def mark_answered(case: CaseFrame, new_slots: Dict[str, str]):
    for k, v in new_slots.items():
        if k.startswith("_"):
            continue
        case.slots[k] = v
        if k not in case.answered:
            case.answered.append(k)
        if k == "prazo_defesa":
            case.deadline = v
    if "_budget_tone" in new_slots:
        case.budget_tone = new_slots["_budget_tone"]
    if "_buy_signal" in new_slots:
        case.buy_signal = True

def missing_slots(case: CaseFrame) -> List[str]:
    req = CASE_REQUIRED_SLOTS.get((case.area, case.subtype), [])
    return [s for s in req if s not in case.answered]

def ask_once(case: CaseFrame, slot: str, question: str) -> Optional[str]:
    # Não repete perguntas já feitas e ainda não respondidas
    if slot in case.answered:
        return None
    if slot in case.asked:
        return None
    case.asked[slot] = question
    return question

def next_stage(case: CaseFrame):
    # Se já tem slots essenciais preenchidos, ir para oferta
    miss = missing_slots(case)
    if case.buy_signal:
        case.stage = "offer"
        return
    if case.stage == "triage":
        case.stage = "collect" if miss else "offer"
    elif case.stage == "collect":
        case.stage = "collect" if miss else "offer"
    elif case.stage == "offer":
        # se usuário demonstrou intenção/price, ir a closing
        case.stage = "closing"
    # closing permanece

def compose_message(case: CaseFrame) -> str:
    text_parts: List[str] = []
    miss = missing_slots(case)

    # Recap automático se conversa "fria"
    if case.needs_recap():
        case.asked = {k: v for k, v in case.asked.items() if k in case.answered}
        resumo = []
        if case.slots.get("prazo_defesa"):
            resumo.append(f"prazo até {case.slots['prazo_defesa']}")
        if "oferta_exame_alternativo" in case.slots:
            if case.slots["oferta_exame_alternativo"] == "não":
                resumo.append("sem oferta de exame alternativo")
            elif case.slots["oferta_exame_alternativo"] == "sim":
                resumo.append("houve oferta de exame alternativo")
        if case.slots.get("assinou_ciencia") == "sim":
            resumo.append("assinou apenas ciência")
        if resumo:
            text_parts.append("Resumo do que já tenho: " + "; ".join(resumo) + ".")
        if miss:
            slot = miss[0]
            desc = MISSING_DESCRIPTIONS.get(slot, f"confirmar {slot}")
            text_parts.append(f"Falta apenas {desc}.")
        offer = build_offer_text(
            area=case.area,
            subtype=case.subtype,
            budget_tone=case.budget_tone,
            deadline=case.deadline,
        )
        text_parts.append(offer)
        text_parts.append("Posso já iniciar pelo Plano Essencial enquanto isso. Fechamos assim?")
        return "\n\n".join(text_parts)

    if case.stage in ("triage", "collect") and miss:
        unasked = [s for s in miss if s not in case.asked]
        if unasked:
            slot = unasked[0]
            question = QUESTION_TEXTS.get(slot, f"Pode confirmar {slot}?")
            q = ask_once(case, slot, question)
            if q:
                if not case.value_drop_done:
                    text_parts.append(
                        "Entendi seu caso e dá pra atacar por vícios formais (sem oferta de exame alternativo, campos do etilômetro em branco etc.)."
                    )
                    case.value_drop_done = True
                text_parts.append(q)
                return "\n\n".join(text_parts)
        else:
            offer = build_offer_text(
                area=case.area,
                subtype=case.subtype,
                budget_tone=case.budget_tone,
                deadline=case.deadline,
            )
            text_parts.append(offer)
            text_parts.append("Enquanto você separa os documentos, posso começar pelo **Plano Essencial**. Fechamos assim?")
            return "\n\n".join(text_parts)

    # Pivô comercial
    if case.stage in ("offer", "closing"):
        offer = build_offer_text(
            area=case.area,
            subtype=case.subtype,
            budget_tone=case.budget_tone,
            deadline=case.deadline,
        )
        text_parts.append(offer)
        # CTA claro
        text_parts.append("Posso iniciar sua defesa **hoje**. Prefere começar pelo Plano Essencial ou Intermediário?")
        return "\n\n".join(text_parts)

    # Fallback (deve quase nunca acontecer)
    return "Para garantir sua defesa no prazo, me confirme a data-limite da notificação, por favor."
    

def handle_message(phone: str, user_text: str, ts: Optional[str] = None) -> str:
    case = load_case(phone) or CaseFrame(phone=phone)
    if not case.deadline and case.slots.get("prazo_defesa"):
        case.deadline = case.slots["prazo_defesa"]
    detect_case(user_text, case)
    new = extract_slots(user_text)
    mark_answered(case, new)
    # Decide próximo estágio
    next_stage(case)

    # Gera mensagem
    reply = compose_message(case)

    miss = missing_slots(case)
    logger.info(
        "orchestrator_state phone=%s stage=%s missing=%s asked_keys=%s answered_keys=%s buy_signal=%s",
        case.phone,
        case.stage,
        miss,
        sorted(case.asked.keys()),
        sorted(case.answered),
        case.buy_signal,
    )

    case.last_user_at = ts or datetime.utcnow().isoformat()
    case.last_bot_at = datetime.utcnow().isoformat()
    save_case(case)
    return reply