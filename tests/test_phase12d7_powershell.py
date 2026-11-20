"""E0-05 (Phase 12D7): phase12-test.ps1 passes docker compose arguments as arrays.

``Invoke-Compose`` collected its arguments with ``ValueFromRemainingArguments``.
That made it an ADVANCED function, which has PowerShell's common parameters:
in ``Invoke-Compose up -d`` PowerShell bound ``-d`` to ``-Debug``, so docker got
``up`` without ``-d`` and the script stayed attached to the containers (12E0).
Now every call passes ONE explicit array (``-ComposeArgs @(...)``,
``Invoke-Exec -Cmd @(...)``): inside an array an element is a value, never a
parameter name.

The Cloud environment has no PowerShell: these are STRUCTURAL checks of the
script text. That ``-d`` reaches docker on Windows PowerShell 5.1 and 7 is a
Windows checklist item (PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / "scripts" / "windows" / "phase12-test.ps1"
BUILD_PS1 = ROOT / "scripts" / "offline" / "build-package.ps1"

ARRAY = re.compile(r"Invoke-Compose -ComposeArgs @\(([^)]*)\)")
ACTION = re.compile(r"^    '([a-z-]+)' \{|^    \{ \$_ -in @\(([^)]*)\) \} \{")
FORBIDDEN = {
    "down",
    "rm",
    "kill",
    "-v",
    "-V",
    "--volumes",
    "--renew-anon-volumes",
    "--remove-orphans",
    "pull",
    "--pull",
    "prune",
}


def _code(path: Path) -> list[str]:
    """Script lines without comments (help block and # comments)."""
    text = re.sub(r"<#.*?#>", "", path.read_text(encoding="utf-8"), flags=re.S)
    return [
        line.split(" #")[0]
        for line in text.splitlines()
        if not line.lstrip().startswith("#")
    ]


def _elements(literal: str) -> list[str]:
    return re.findall(r"'([^']*)'", literal)


def _compose_arrays() -> dict[str, list[list[str]]]:
    """{action: [array of each Invoke-Compose call in it]} (definitions excluded)."""
    found: dict[str, list[list[str]]] = {}
    action = "(top level)"
    for line in _code(PS1):
        m = ACTION.match(line)
        if m:
            action = m.group(1) or ",".join(_elements(m.group(2)))
        for literal in ARRAY.findall(line):
            found.setdefault(action, []).append(_elements(literal))
    return found


def test_no_function_collects_its_remaining_arguments():
    for path in (PS1, BUILD_PS1):
        assert not [
            line for line in _code(path) if "ValueFromRemainingArguments" in line
        ], path


def test_every_compose_and_exec_call_passes_one_explicit_array():
    calls = [
        line.strip()
        for line in _code(PS1)
        if re.search(r"\bInvoke-(Compose|Exec)\b", line) and "function " not in line
    ]
    assert calls, "no call found"
    for line in calls:
        for name, param in (
            ("Invoke-Compose", "-ComposeArgs"),
            ("Invoke-Exec", "-Cmd"),
        ):
            for use in re.findall(rf"{name}\b[^;}}]*", line):
                assert use.startswith(f"{name} {param} @(") or use.startswith(
                    f"{name} {param} ("
                ), use


def test_up_keeps_detached_and_the_app_only_actions_touch_only_the_app():
    arrays = _compose_arrays()
    assert arrays["up"] == [["up", "-d"]]
    app_only = [
        "up",
        "-d",
        "--no-deps",
        "--no-build",
        "--force-recreate",
        "open_notebook",
    ]
    assert arrays["legal-gate"] == [app_only]
    assert arrays["restart-app"] == [app_only]
    assert arrays["build"] == [["build", "open_notebook"]]
    assert arrays["stop"] == [["stop"]]
    assert arrays["logs"] == [["logs", "--tail", "200", "open_notebook"]]
    assert arrays["status"] == [["ps"]]


def test_no_destructive_or_pulling_compose_argument():
    for action, calls in _compose_arrays().items():
        for args in calls:
            assert not FORBIDDEN & set(args), (action, args)
    text = "\n".join(_code(PS1))
    for bad in ("compose down", "volume rm", "system prune", "Remove-Item"):
        assert bad not in text


def test_exec_goes_through_the_app_container_with_t():
    text = "\n".join(_code(PS1))
    assert (
        "Invoke-Compose -ComposeArgs (@('exec', '-T', 'open_notebook') + $Cmd)" in text
    )


def test_orientation_action_runs_the_e1_05_tool_with_checked_suspects():
    text = "\n".join(_code(PS1))
    assert "'orientation' { 'scripts/ocr/phase12_orientation_diagnose.py' }" in text
    assert "$extra += @('--suspect', $s)" in text
    assert "if ($NoText) { $extra += '--no-text' }" in text
    assert re.search(
        r"-notmatch '\^\\d\+:\[0-9\.\]\+,", text
    )  # the suspect shape is checked
