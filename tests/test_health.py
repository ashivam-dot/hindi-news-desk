import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("health_check", Path(__file__).resolve().parents[1] / ".github" /
                                              "health_check.py")
health_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(health_check)
NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def write(tmp_path, **health):
    path = tmp_path / "health.json"
    path.write_text(json.dumps({"at": "2026-10-10T11:30:00+00:00", "ok": True} | health))
    return path


def test_healthy(tmp_path):
    assert health_check.problem(write(tmp_path), NOW) is None


def test_silent_failed_or_holding(tmp_path):
    assert "No desk run" in health_check.problem(write(tmp_path, at="2026-10-10T06:00:00+00:00"), NOW)
    assert "failed" in health_check.problem(write(tmp_path, ok=False, error="boom"), NOW)
    assert "holding" in health_check.problem(write(tmp_path, held="hold: no Sulafat voice"), NOW)


def test_a_new_desk_without_a_health_file_is_not_an_alert(tmp_path, capsys):
    assert health_check.problem(tmp_path / "nope.json", NOW) is None
    assert "missing" in capsys.readouterr().out
