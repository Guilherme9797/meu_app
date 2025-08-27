import pytest

from server import _coerce_text

@pytest.mark.parametrize(
    "value,expected",
    [
        (" hello ", "hello"),
        (b"oi\n", "oi"),
        ({"text": "hi"}, "hi"),
        ({"message": {"text": "x"}}, "x"),
        ([" a ", {"text": "b"}], "a b"),
    ],
)
def test_coerce_text_handles_various_inputs(value, expected):
    assert _coerce_text(value) == expected