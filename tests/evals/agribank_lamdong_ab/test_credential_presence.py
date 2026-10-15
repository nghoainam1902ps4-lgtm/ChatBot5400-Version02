"""Regression test for the A/B runner credential-presence gate.

Guards the exact bug that halted workflow run 37713748880: the workflow maps the
secret to AB_API_KEY, but credential_present() did not recognize AB_API_KEY, so
the pre-flight dry-run reported CREDENTIAL = ABSENT and never ran.

No real provider calls. No production DB. The fake value is never printed.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "run_real_ab_under_test", _HERE / "run_real_ab.py"
)
run_real_ab = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = run_real_ab
_spec.loader.exec_module(run_real_ab)

# Every env var the gate inspects — cleared for isolation in each test.
_CRED_VARS = (
    "AB_API_KEY",
    "ANTHROPIC_COMPATIBLE_API_KEY", "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY", "OPENAI_COMPATIBLE_API_KEY",
    "GEMINI_API_KEY", "GROQ_API_KEY", "OLLAMA_BASE_URL",
)

_FAKE = "test-not-a-real-key"  # synthetic; never printed


@pytest.fixture
def clean_env(monkeypatch):
    for k in _CRED_VARS:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def test_absent_when_no_credential(clean_env):
    assert run_real_ab.credential_present() is False


def test_present_when_only_ab_api_key(clean_env):
    clean_env.setenv("AB_API_KEY", _FAKE)
    assert run_real_ab.credential_present() is True


@pytest.mark.parametrize("var", _CRED_VARS)
def test_present_for_each_recognized_var(clean_env, var):
    clean_env.setenv(var, _FAKE)
    assert run_real_ab.credential_present() is True


def test_does_not_leak_value(clean_env, capsys):
    clean_env.setenv("AB_API_KEY", _FAKE)
    assert run_real_ab.credential_present() is True
    captured = capsys.readouterr()
    assert _FAKE not in captured.out
    assert _FAKE not in captured.err
