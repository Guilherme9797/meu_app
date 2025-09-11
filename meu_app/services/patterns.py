from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Iterable, Tuple
import re, unicodedata, json, os, glob, time

# ========== Normalização ==========
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower().strip())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s)


def _labelize(s: str) -> str:
    return _norm(s.replace("/", " ").replace("\\", " ").replace("-", " ").replace("_", " "))


def _variants(token: str) -> List[str]:
    t = token.strip()
    if not t:
        return []
    v = {t, t.replace("_", " "), t.replace("_", "")}
    return list(v)

# ========== Rule model ==========

@dataclass
class PatternRule:
    name: str
    any_of: List[str]
    none_of: List[str] = field(default_factory=list)
    dominios: List[str] = field(default_factory=list)
    institutes: List[str] = field(default_factory=list)
    bens: List[str] = field(default_factory=list)
    atos: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


# ========= Mapeamento de domínios (chave de topo -> domínios amplos do orquestrador) =========

_TOP_TO_DOMAIN = {
    # substantivos
    "direito_civil": ["civil"],
    "direito_processual_civil": ["processual_civil"],
    "direito_penal": ["penal"],
    "direito_penal_parte_geral": ["penal"],
    "direito_penal_parte_especial": ["penal"],
    "direito_processual_penal": ["processual_penal"],
    "direito_tributario": ["tributário"],
    "direito_empresarial": ["empresarial"],
    "direito_previdenciario": ["previdenciário"],
    "direito_administrativo": ["administrativo"],
    "direito_ambiental": ["ambiental"],
    "direito_do_consumidor": ["consumidor"],
    "direito_imobiliario": ["imobiliário", "civil"],
    "direito_do_trabalho": ["trabalho"],
    "direito_processual_do_trabalho": ["processual_trabalho"],
    "direito_de_familia": ["família"],
    "direito_das_sucessoes": ["sucessões"],
     # variações
    "civil": ["civil"], "processual_civil": ["processual_civil"], "penal": ["penal"],
    "processual_penal": ["processual_penal"], "tributario": ["tributário"],
    "empresarial": ["empresarial"], "previdenciario": ["previdenciário"],
    "administrativo": ["administrativo"], "ambiental": ["ambiental"],
    "consumidor": ["consumidor"], "imobiliario": ["imobiliário", "civil"],
    "trabalho": ["trabalho"], "processual_trabalho": ["processual_trabalho"],
    "familia": ["família"], "sucessoes": ["sucessões"],
}
def _dominios_for_topkey(k: str) -> List[str]:
    k = _norm(k).replace(" ", "_")
    return _TOP_TO_DOMAIN.get(k, [])

# ========== Taxonomy walking ==========

def _iter_taxonomy(tree: Any, path: List[str]) -> Iterable[Tuple[List[str], str | None]]:
    if isinstance(tree, dict):
        for k, v in tree.items():
            yield from _iter_taxonomy(v, path + [k])
    elif isinstance(tree, list):
        for leaf in tree:
            if isinstance(leaf, str):
                yield (path, leaf)
            else:
                yield from _iter_taxonomy(leaf, path)
    elif isinstance(tree, str):
        yield (path, tree)

def rules_from_taxonomy(tax: Dict[str, Any]) -> List[PatternRule]:
    rules: List[PatternRule] = []
    if not isinstance(tax, dict):
        return rules

    for top, subtree in tax.items():
        dominios = _dominios_for_topkey(top) or []
        for path, leaf in _iter_taxonomy(subtree, [top]):
            labels = [_labelize(seg) for seg in path[1:]]  # sem topo
            leaf_lbl = _labelize(leaf) if leaf else None
            triggers: Set[str] = set()
            if leaf_lbl:
                triggers.update(_variants(leaf_lbl.replace(" ", "_")))
            path_tokens = [lbl.replace(" ", "_") for lbl in labels]
            for seg in path_tokens:
                triggers.update(_variants(seg))
            if path_tokens:
                triggers.update(_variants("_".join(path_tokens)))
            institutes = labels[:] + ([leaf_lbl] if leaf_lbl else [])
            bens, atos = [], []
            joined = " ".join(institutes)
            if any(x in joined for x in ["imovel", "imobiliario", "condominio", "usucapiao", "matricula", "registro"]):
                bens.append("imóvel")
            if any(x in joined for x in ["veiculo", "ipva", "detran"]):
                bens.append("veículo")
            if "adjudicacao" in joined:
                atos.append("ajuizar adjudicação compulsória")
            if any(x in joined for x in ["obrigacao de fazer", "registro", "transferencia", "outorga"]):
                atos.append("obrigação de fazer (cumprimento específico)")
            name = "/".join([_labelize(p) for p in path] + ([leaf_lbl] if leaf_lbl else []))
            if triggers:
                rules.append(
                    PatternRule(
                        name=name,
                        any_of=sorted(triggers),
                        dominios=sorted(set(dominios)),
                        institutes=sorted({*institutes}),
                        bens=sorted(set(bens)),
                        atos=sorted(set(atos)),
                    )
                )
    return rules

# ========== Loader robusto (arquivo único com multi-JSON) ==========

def _load_many_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        s = f.read().strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    decoder = json.JSONDecoder()
    idx, merged = 0, {}
    while idx < len(s):
        s = s[idx:].lstrip()
        if not s:
            break
        try:
            obj, end = decoder.raw_decode(s)
        except Exception:
            break
        if isinstance(obj, dict):
            merged = _deep_merge(merged, obj)
        idx = end
    return merged

# ========== Merge recursivo para N arquivos ==========
def _deep_merge(a: Any, b: Any) -> Any:
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = _deep_merge(out.get(k), v)
        return out
    if isinstance(a, list) and isinstance(b, list):
        # concat com dedup preservando ordem
        seen, out = set(), []
        for x in a + b:
            key = json.dumps(x, ensure_ascii=False, sort_keys=True) if not isinstance(x, str) else x
            if key not in seen:
                seen.add(key)
                out.append(x)
        return out
    return b if b is not None else a

# ========== Carregadores ==========
def load_rules_from_taxonomy_file(path: str) -> List[PatternRule]:
    if not path or not os.path.isfile(path):
        return []
    try:
        tax = _load_many_json(path)
        return rules_from_taxonomy(tax)
    except Exception:
        return []


# ========= Loader “antigo” (lista direta de PatternRule em JSON) =========


def load_rules_from_taxonomy_dir(dirpath: str) -> List[PatternRule]:
    if not dirpath or not os.path.isdir(dirpath):
        return []
    merged: Dict[str, Any] = {}
    for fp in sorted(glob.glob(os.path.join(dirpath, "*.json"))):
        try:
            merged = _deep_merge(merged, _load_many_json(fp))
        except Exception:
            continue
    return rules_from_taxonomy(merged)

def load_rules_from_taxonomy_path_or_dir(path_or_dir: str) -> List[PatternRule]:
    if not path_or_dir:
        return []
    if os.path.isdir(path_or_dir):
        return load_rules_from_taxonomy_dir(path_or_dir)
    return load_rules_from_taxonomy_file(path_or_dir)

# ========== Hot-reload por mtime ==========
_TAX_PATH_ENV = os.getenv("MEU_APP_TAXONOMIA_DIR") or os.getenv("MEU_APP_TAXONOMIA_EXTENSA") or ""
_TAX_LAST_SIG = 0.0
_EXTRA_RULES_CACHE: List[PatternRule] = []

def _dir_signature(path: str) -> float:
    if os.path.isdir(path):
        mt = [os.path.getmtime(p) for p in glob.glob(os.path.join(path, "*.json"))]
        return max(mt) if mt else 0.0
    if os.path.isfile(path):
        return os.path.getmtime(path)
    return 0.0

def _maybe_reload_taxonomy() -> None:
    global _TAX_LAST_SIG, _EXTRA_RULES_CACHE
    if not _TAX_PATH_ENV:
        return
    sig = _dir_signature(_TAX_PATH_ENV)
    if sig > _TAX_LAST_SIG:
        _EXTRA_RULES_CACHE = load_rules_from_taxonomy_path_or_dir(_TAX_PATH_ENV)
        _TAX_LAST_SIG = sig

# ========== Regras base ==========

BASE_RULES: List[PatternRule] = [
    PatternRule(
        name="inadimplemento_contratual",
        any_of=["inadimplemento", "descumprimento", "multa_contratual", "quebrou_contrato"],
        dominios=["civil", "processual_civil"],
        institutes=["responsabilidade contratual", "resolução contratual", "cumprimento específico"],
        atos=["notificar extrajudicialmente", "ajuizar obrigação de fazer ou pagar"],
        keywords=["cpc 497", "cpc 536"],
    ),
    PatternRule(
        name="danos_materiais_e_morais",
        any_of=["dano_moral", "dano_material", "indenizacao", "lucros_cessantes"],
        dominios=["civil", "consumidor", "trabalho"],
        institutes=["responsabilidade civil"],
        atos=["quantificar danos", "ajuizar indenização"],
    ),
]
def _all_rules() -> List[PatternRule]:
    _maybe_reload_taxonomy()
    return BASE_RULES + _EXTRA_RULES_CACHE

# ========== Aplicação ==========
def apply_patterns(text: str, extra_rules: List[PatternRule] | None = None) -> Dict[str, List[str]]:
    """
    Retorna um frame bruto a partir do texto, disparando todas as PatternRules.
    Inclui hot-reload automático dos JSONs se MEU_APP_TAXONOMIA_DIR/EXTENSA estiver setado.
    """
    p = _norm(text)
    rules = _all_rules() + (extra_rules or [])
    dom: Set[str] = set()
    inst: Set[str] = set()
    bens: Set[str] = set()
    atos: Set[str] = set()
    kw: Set[str] = set()

    for rule in rules:
        if any(_norm(tok) in p for tok in rule.any_of) and not any(_norm(tok) in p for tok in rule.none_of):
            dom.update(rule.dominios)
            inst.update(rule.institutes)
            bens.update(rule.bens)
            atos.update(rule.atos)
            kw.update(rule.keywords)

    return {
        "dominios": sorted(dom),
        "institutos": sorted(inst),
        "bens_relacionados": sorted(bens),
        "atos_centrais": sorted(atos),
        "palavras_chave": sorted(kw),
    }