"""Slips in the model's JSON that mean the right thing are put right, and rate limits are waited out."""

from circuitmind.failure import plain_engine_error
from circuitmind.providers import retry_wait_seconds, to_design_dict

BOARD = "wokwi-esp32-devkit-v1"


def test_board_written_as_esp_becomes_the_board_type():
    d = to_design_dict({"board": "esp", "parts": [], "connections": []}, board=BOARD)
    assert d["board"] == BOARD


def test_missing_board_is_filled_in():
    d = to_design_dict({"parts": [], "connections": []}, board=BOARD)
    assert d["board"] == BOARD


def test_board_type_used_as_connection_prefix_becomes_esp():
    wire = {"board": BOARD, "parts": [],
            "connections": [{"from": f"{BOARD}:D2", "to": "r1:1"}, [f"{BOARD}:GND.1", "led1:C"]]}
    d = to_design_dict(wire, board=BOARD)
    assert d["connections"] == [("esp:D2", "r1:1"), ("esp:GND.1", "led1:C")]


def test_other_boards_are_left_alone():
    d = to_design_dict({"board": "wokwi-pi-pico", "parts": [], "connections": [["esp:D2", "r1:1"]]}, board=BOARD)
    assert d["board"] == "wokwi-pi-pico"
    assert d["connections"] == [("esp:D2", "r1:1")]


def test_attrs_list_becomes_dict():
    d = to_design_dict({"board": BOARD, "parts": [{"id": "led1", "type": "wokwi-led",
                                                   "attrs": [{"key": "color", "value": "red"}]}],
                        "connections": []}, board=BOARD)
    assert d["parts"][0]["attrs"] == {"color": "red"}


def test_groq_try_again_hint_is_honoured():
    text = '{"error":{"message":"Rate limit reached ... Please try again in 3.5925s. Need more tokens?"}}'
    assert abs(retry_wait_seconds(429, text, None, 0) - 4.5925) < 1e-6


def test_retry_after_header_is_honoured_and_capped():
    assert retry_wait_seconds(429, "", {"Retry-After": "12"}, 0) == 13
    assert retry_wait_seconds(429, "try again in 5m", None, 0) == 45


def test_other_errors_back_off():
    assert retry_wait_seconds(503, "", None, 0) == 2
    assert retry_wait_seconds(503, "", None, 2) == 5


def test_engine_errors_become_sentences():
    msg = plain_engine_error(RuntimeError("groq HTTP 429: tokens per minute (TPM): Limit 8000"))
    assert msg.startswith("The free model service is busy")
    assert "HTTP 429" in msg
    assert plain_engine_error(RuntimeError("groq daily quota exhausted: x")).startswith("The free model quota")
    assert plain_engine_error(ValueError("boom")).startswith("Something broke")
