from meu_app.services.atendimento_orchestrator import AtendimentoOrchestrator


def test_fallback_to_pitch_on_generic_response(monkeypatch):
    """Se a resposta legal ficar genérica e a cobertura for baixa, usa o pitch."""

    class DummyInterpreter:
        def parse(self, mensagem):
            return type("Frame", (), {"queries": []})

    class DummyBuscador:
        def __init__(self, logger=None):
            pass

        def search_hybrid(self, queries, top_k=12, bm25=True, semantic=True):
            return [], 0.5

    class DummyLegal:
        def __init__(self, llm=None, logger=None):
            pass

        def compose(self, mensagem, frame, pack, coverage):
            return "Diagnóstico teste\nO que fazer agora: nada"

    class DummyPitch:
        def __init__(self, llm=None, logger=None, branding=None):
            self.called = False

        def compose(self, mensagem, extra_context=None):
            self.called = True
            return "pitch"

    # Substitui dependências internas por dummies
    monkeypatch.setattr(
        "meu_app.services.atendimento_orchestrator.UniversalInterpreter", DummyInterpreter
    )
    monkeypatch.setattr("meu_app.services.atendimento_orchestrator.BuscadorPDF", DummyBuscador)
    monkeypatch.setattr("meu_app.services.atendimento_orchestrator.LegalComposer", DummyLegal)
    monkeypatch.setattr(
        "meu_app.services.atendimento_orchestrator.ClientPitchGenerator", DummyPitch
    )

    orch = AtendimentoOrchestrator(llm=None, logger=None)
    resp = orch.handle("teste", {})

    assert resp == "pitch"
    assert orch.pitch.called
