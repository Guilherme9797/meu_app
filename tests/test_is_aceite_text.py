import pytest
from server import _is_aceite_text

@pytest.mark.parametrize(
    "msg, expected",
    [
        ("aceito", True),
        ("ok pode seguir", True),
        ("não aceito", False),
        ("nao, pode seguir", False),
    ],
)
def test_is_aceite_text_detects_acceptance(msg, expected):
    assert _is_aceite_text(msg) is expected