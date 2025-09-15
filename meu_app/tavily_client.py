import os, re, io, requests
from typing import Optional
try:
    import pdfplumber  # pip install pdfplumber
except Exception:
    pdfplumber = None

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

def _tavily_search(query: str) -> Optional[str]:
    if not TAVILY_API_KEY:
        return None
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": TAVILY_API_KEY, "query": query, "max_results": 5},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("results", []):
            url = r.get("url","")
            if "oabgo.org.br" in url and url.endswith(".pdf"):
                return url
        # fallback: retorna o primeiro PDF da OAB-GO
        for r in data.get("results", []):
            url = r.get("url","")
            if "oabgo.org.br" in url and ".pdf" in url:
                return url
        return None
    except Exception:
        return None

def _download(url: str) -> Optional[bytes]:
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.content
    except Exception:
        return None

def find_min_fee_in_pdf(pdf_bytes: bytes, label: str) -> Optional[float]:
    if not pdfplumber:
        return None
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            # heurística simples: linha com label aproximada e número com R$ ou 0,00
            if re.search(label[:10], text, re.IGNORECASE):
                m = re.search(r"R\$\s*([\d\.\,]+)", text)
                if m:
                    raw = m.group(1).replace(".","").replace(",",".")
                    try:
                        return float(raw)
                    except Exception:
                        pass
    return None

def fetch_minimum_for_label(label: str) -> Optional[float]:
    url = _tavily_search("Tabela de Honorários Mínimos OAB-GO 2025 PDF " + label)
    if not url:
        return None
    pdf = _download(url)
    if not pdf:
        return None
    return find_min_fee_in_pdf(pdf, label)