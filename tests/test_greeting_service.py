from datetime import datetime

from meu_app.services.greeting_service import generate_human_greeting


def test_generate_greeting_with_name():
    msg = generate_human_greeting(None, name="Ana", brand="Brand", now_local=datetime.now())
    assert "Ana" in msg
    assert "Brand" in msg


def test_generate_greeting_without_name_asks():
    msg = generate_human_greeting(None, name=None, brand="Brand", now_local=datetime.now())
    assert "Qual é o seu nome" in msg