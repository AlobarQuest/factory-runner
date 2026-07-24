import json

from factory_runner.coding_result import CostActuals, extract_cost_actuals


def _write(tmp_path, records):
    p = tmp_path / "exec.json"
    p.write_text(json.dumps(records))
    return p


def test_extracts_usage_from_terminal_result(tmp_path):
    path = _write(
        tmp_path,
        [
            {"type": "assistant", "message": {}},
            {"type": "assistant", "message": {}},
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "num_turns": 5,
                "total_cost_usd": 4.25,
                "usage": {"input_tokens": 1000, "output_tokens": 200},
            },
        ],
    )
    actuals = extract_cost_actuals(path)
    assert actuals == CostActuals(
        cost_known=True,
        llm_calls=2,
        num_turns=5,
        input_tokens=1000,
        output_tokens=200,
        cost_usd=4.25,
    )


def test_missing_file_is_unknown(tmp_path):
    actuals = extract_cost_actuals(tmp_path / "does-not-exist.json")
    assert actuals.cost_known is False
    assert actuals.llm_calls is None
    assert actuals.cost_usd is None


def test_no_terminal_result_is_unknown(tmp_path):
    path = _write(tmp_path, [{"type": "assistant", "message": {}}])
    assert extract_cost_actuals(path).cost_known is False
