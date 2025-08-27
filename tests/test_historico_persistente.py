import importlib

def test_historico_persistente_normalizes_keys(tmp_path, monkeypatch):
    db_file = tmp_path / "db.sqlite"
    monkeypatch.setenv("APP_DB_PATH", str(db_file))

    # reload modules so DB_PATH picks up new env var
    db_module = importlib.reload(__import__("meu_app.persistence.db", fromlist=["*"]))
    repo_module = importlib.reload(__import__("meu_app.persistence.repositories", fromlist=["*"]))
    historico_module = importlib.reload(__import__("meu_app.models.historico", fromlist=["*"]))

    HistoricoConversaPersistente = historico_module.HistoricoConversaPersistente

    hist = HistoricoConversaPersistente("cliente1")
    hist.registrar_mensagem("cliente", "Oi")
    hist.registrar_mensagem("assistente", "Olá")

    dados = hist.obter_historico()
    assert dados[0]["autor"] == "cliente"
    assert dados[0]["mensagem"] == "Oi"
    assert dados[1]["autor"] == "assistente"
    assert dados[1]["mensagem"] == "Olá"
    assert dados[0]["timestamp"]