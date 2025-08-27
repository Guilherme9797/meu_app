from datetime import datetime

class HistoricoConversa:
    def __init__(self):
        self.conversas = []

    def registrar_mensagem(self, autor: str, mensagem: str):
        self.conversas.append({
            "autor": autor,
            "mensagem": mensagem,
            "timestamp": datetime.now().isoformat()
        })

    def obter_historico(self):
        return self.conversas

    def __repr__(self):
        return "\n".join([f"[{c['timestamp']}] {c['autor']}: {c['mensagem']}" for c in self.conversas])

# ===== Histórico persistente (usa SQLite via repositories) =====
try:
    # quando importado dentro do pacote
    from ..persistence.repositories import MensagemRepository
except Exception:
    # fallback quando o script roda direto e __package__ pode estar vazio
    from meu_app.persistence.repositories import MensagemRepository  # type: ignore

class HistoricoConversaPersistente:
    def __init__(self, cliente_id: str, repo: 'MensagemRepository | None' = None):
        self.cliente_id = cliente_id
        self.repo = repo or MensagemRepository()

    def registrar_mensagem(self, autor: str, mensagem: str, meta: dict | None = None):
        # 'autor' deve ser algo como 'cliente', 'assistente' ou 'sistema'
        self.repo.adicionar(self.cliente_id, autor, mensagem, meta)

    def obter_historico(self):
        raw = self.repo.get_history(self.cliente_id)
        normalized = []
        for r in raw:
            normalized.append(
                {
                    "autor": r.get("autor") or r.get("role"),
                    "mensagem": r.get("mensagem") or r.get("content"),
                    "timestamp": r.get("timestamp") or r.get("created_at"),
                    "meta": r.get("meta"),
                }
            )
        return normalized
