import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .storage import load_case, save_case
from .generative_playbook import generate_playbook
from .sales import build_offer_from_playbook

HOURS_FOR_RECAP = 72
QUESTION_COOLDOWN_SEC = 90

logger = logging.getLogger(__name__)

@dataclass
class CaseFrame:
    phone: str
    area: str = ""
    subtype: str = ""
    stage: str = "triage"
    slots: Dict[str, str] = field(default_factory=dict)
    asked: Dict[str, str] = field(default_factory=dict)
    answered: List[str] = field(default_factory=list)
    budget_tone: Optional[str] = None
    deadline: Optional[str] = None
    last_user_at: Optional[str] = None
    last_bot_at: Optional[str] = None
    buy_signal: bool = False
    value_drop_done: bool = False
    last_question_slot: Optional[str] = None
    last_question_at: Optional[str] = None

    playbook: Optional[Dict] = None  # Playbook serializado

    def now(self) -> datetime:
        return datetime.utcnow()

    def needs_recap(self) -> bool:
        if not self.last_user_at:
            return False
        last = datetime.fromisoformat(self.last_user_at)
        return (self.now() - last) > timedelta(hours=HOURS_FOR_RECAP)

def _cooldown_ok(case: CaseFrame, slot: str) -> bool:
    if case.last_question_slot != slot or not case.last_question_at:
        return True
    try:
        dt = datetime.fromisoformat(case.last_question_at)
        return (datetime.utcnow() - dt).total_seconds() >= QUESTION_COOLDOWN_SEC
    except Exception:
        return True

def extract_slots(text: str) -> Dict[str, str]:
    import re
    t = text.lower()
    out: Dict[str,str] = {}

    # sinais de orçamento/comercial
    if any(k in t for k in ["preço", "preco", "honorár", "honorar", "valor", "quanto custa", "parcel"]):
        out["_buy_signal"] = "1"
    if any(k in t for k in ["apertado", "mais barato", "parcel", "desconto"]):
        out["_budget_tone"] = "apertado"

    # datas comuns: dd/mm/aaaa
    m = re.search(r"(\d{2}/\d{2}/\d{4})", t)
    if m:
        out["data"] = m.group(1)
        # heurística: se houver 'audiên' próximo
        if "audiên" in t or "audien" in t:
            out["data_audiencia"] = m.group(1)
            out["prazo"] = m.group(1)
        if "prazo" in t or "até" in t or "limite" in t:
            out["prazo"] = m.group(1)

    # documentos
    if any(k in t for k in ["pdf", "foto", "print", "cópia", "copia", "anexo"]):
        out["documentos"] = "sim"

    return out

def ensure_playbook(case: CaseFrame, user_text: str):
    regenerate = False
    if not case.playbook:
        regenerate = True
    # se conversa esfriou, regenerar (pode mudar CTA, perguntas)
    if case.needs_recap():
        regenerate = True
    if regenerate:
        pb = generate_playbook(user_text, case)
        case.playbook = {
            "area": pb.area, "subtype": pb.subtype,
            "goals": pb.goals, "risks": pb.risks,
            "required_slots": pb.required_slots,
            "questions": pb.questions,
            "pricing_services": pb.pricing_services,
            "cta": pb.cta, "created_at": pb.created_at, "version": pb.version
        }
        # propagar área/subtipo para analytics
        case.area = case.area or pb.area
        case.subtype = case.subtype or pb.subtype

def mark_answered(case: CaseFrame, new_slots: Dict[str, str]):
    for k, v in new_slots.items():
        if k.startswith("_"):
            continue
        case.slots[k] = v
        if k not in case.answered:
            case.answered.append(k)
        if k in case.asked:
            case.asked.pop(k, None)
        if case.last_question_slot == k:
            case.last_question_slot = None
            case.last_question_at = None
        if k in ("prazo","prazo_defesa","data_audiencia"):
            case.deadline = v
    if "_budget_tone" in new_slots:
        case.budget_tone = new_slots["_budget_tone"]
    if "_buy_signal" in new_slots:
        case.buy_signal = True

def missing_slots(case: CaseFrame) -> List[str]:
    req = []
    if case.playbook and case.playbook.get("required_slots"):
        req.extend(case.playbook["required_slots"])
    # slots universais úteis sempre
    for g in ["prazo","documentos","objetivo","orçamento"]:
        if g not in req:
            req.append(g)
    return [s for s in req if s not in case.answered]

def compose_message(case: CaseFrame) -> str:
    parts: List[str] = []

    # Empatia + valor (uma vez)
    if not case.value_drop_done:
        parts.append("Entendi seu caso — dá pra agir já para reduzir risco e conduzir a melhor saída.")
        case.value_drop_done = True
        # Recap se “fria”
    if case.needs_recap():
        rec = []
        if case.deadline: rec.append(f"prazo/audiência {case.deadline}")
        if case.area or case.subtype: rec.append(f"área: {case.area}/{case.subtype or '—'}")
        if rec: parts.append("Resumo: " + " | ".join(rec) + ".")

    # OFERTA sempre a partir do playbook
    pricing_services = (case.playbook or {}).get("pricing_services", []) if case.playbook else []
    plan_steps = (case.playbook or {}).get("goals", []) if case.playbook else []
    offer = build_offer_from_playbook(pricing_services, plan_steps, case.budget_tone, case.deadline)
    parts.append(offer)

    # CTA curto
    cta = (case.playbook or {}).get("cta") or "Posso iniciar hoje. Prefere o pacote essencial ou intermediário?"
    parts.append(cta)

    # UMA pergunta: priorize slots do playbook
    miss = missing_slots(case)
    q_text = None
    if case.playbook and case.playbook.get("questions"):
        for s in miss:
            if s in case.playbook["questions"] and _cooldown_ok(case, s):
                q_text = case.playbook["questions"][s]
                case.asked[s] = q_text
                case.last_question_slot = s
                case.last_question_at = datetime.utcnow().isoformat()
                break
    # fallback de pergunta global
    if not q_text and miss:
        s = miss[0]
        if _cooldown_ok(case, s):
            default_q = {
                "prazo": "Existe algum prazo ou audiência marcada? Qual a data?",
                "documentos": "Consegue enviar a intimação/BO/contrato aqui (PDF/foto)?",
                "objetivo": "Seu objetivo imediato é acordo, arquivamento, ação ou outra medida?",
                "orçamento": "Prefere à vista com desconto ou parcelado?"
            }
            q_text = default_q.get(s, f"Pode confirmar {s}?")
            case.asked[s] = q_text
            case.last_question_slot = s
            case.last_question_at = datetime.utcnow().isoformat()

    if q_text:
        parts.append(q_text)

    return "\n\n".join(parts)

def handle_message(phone: str, user_text: str, ts: Optional[str] = None) -> str:
    case = load_case(phone) or CaseFrame(phone=phone)

    ensure_playbook(case, user_text)        # <<< gerativo por mensagem
    new = extract_slots(user_text)
    mark_answered(case, new)
    reply = compose_message(case)
    logger.info(
        "state phone=%s stage=%s area=%s subtype=%s asked=%s answered=%s deadline=%s",
        case.phone, case.stage, case.area, case.subtype, list(case.asked.keys()), case.answered, case.deadline
    )
    case.last_user_at = ts or datetime.utcnow().isoformat()
    case.last_bot_at = datetime.utcnow().isoformat()
    save_case(case)

    return reply