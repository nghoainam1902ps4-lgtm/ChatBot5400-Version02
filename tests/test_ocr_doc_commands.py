"""Every ```bash block in docs/ocr must parse (bash -n), and the acceptance
guide must not ask for destructive operations on existing data."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_all_ocr_doc_bash_blocks_parse():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "ocr" / "check_doc_commands.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_acceptance_guide_never_destroys_existing_data():
    blocks = "\n".join(
        re.findall(
            r"```bash\n(.*?)```",
            (ROOT / "docs" / "ocr" / "OCR_LOCAL_ACCEPTANCE.md").read_text(
                encoding="utf-8"
            ),
            re.S,
        )
    )
    assert "down -v" not in blocks
    assert "notebook_data" not in blocks and "surreal_data" not in blocks
    assert "volume rm" not in blocks and "system prune" not in blocks
