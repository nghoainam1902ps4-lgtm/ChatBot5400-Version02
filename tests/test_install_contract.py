"""Static installation-contract tests for ChatBot 5400.

These guard the *canonical* fresh-install path so a future edit can't silently
make `git clone … && docker compose up -d` run upstream Open Notebook's
prebuilt application image instead of building ChatBot 5400 from this repo.

They are deliberately text/regex based (no YAML parse, no heavy deps) and only
flag the dangerous *installation* patterns — a legitimate upstream attribution
link (https://github.com/lfnovo/open-notebook) is allowed and must not trip them.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT_COMPOSE = REPO_ROOT / "docker-compose.yml"
PROD_COMPOSE = REPO_ROOT / "deploy" / "docker-compose.prod.yml"
README = REPO_ROOT / "README.md"

# A YAML `image:` directive pointing at upstream's published app image, e.g.
#   image: lfnovo/open_notebook:v1-latest
# Anchored to the `image:` key so plain-text warnings that merely NAME the image
# ("do NOT use lfnovo/open_notebook:v1-latest") do not match.
UPSTREAM_APP_IMAGE = re.compile(r"^\s*image:\s*lfnovo/open_notebook", re.MULTILINE)

# The upstream Quick Start download that fetches Open Notebook's compose file.
UPSTREAM_COMPOSE_DOWNLOAD = (
    "raw.githubusercontent.com/lfnovo/open-notebook/main/docker-compose.yml"
)


def test_root_compose_does_not_use_upstream_app_image():
    text = ROOT_COMPOSE.read_text(encoding="utf-8")
    assert not UPSTREAM_APP_IMAGE.search(text), (
        "docker-compose.yml must not run the upstream app image "
        "(image: lfnovo/open_notebook:*); it must build ChatBot 5400 from source."
    )


def test_root_compose_builds_app_from_source():
    text = ROOT_COMPOSE.read_text(encoding="utf-8")
    assert re.search(r"^\s*build:", text, re.MULTILINE), (
        "docker-compose.yml app service must build from source (build:)."
    )
    assert re.search(r"dockerfile:\s*Dockerfile", text), (
        "docker-compose.yml must build with the root Dockerfile."
    )
    # The root Dockerfile must exist for that build to resolve.
    assert (REPO_ROOT / "Dockerfile").is_file(), "Root Dockerfile is missing."


def test_readme_does_not_install_via_upstream():
    text = README.read_text(encoding="utf-8")
    assert UPSTREAM_COMPOSE_DOWNLOAD not in text, (
        "README must not instruct users to download the upstream "
        "Open Notebook docker-compose.yml as the ChatBot 5400 install path."
    )
    assert not UPSTREAM_APP_IMAGE.search(text), (
        "README must not present an `image: lfnovo/open_notebook:*` compose "
        "service as the ChatBot 5400 install path."
    )


def _readme_code_blocks(text: str) -> list[str]:
    """Bodies of fenced ``` code blocks (the commands users actually run)."""
    return re.findall(r"```[^\n]*\n(.*?)```", text, re.DOTALL)


def test_readme_local_quickstart_avoids_pre_fix_stable_tag():
    """The local/root-compose Quick Start must route through the default
    development branch, NOT `git checkout v1.0.2` — that frozen release predates
    this fix and its root docker-compose.yml still runs the upstream app image.

    Only *runnable* commands (fenced code blocks) are checked, so the prose
    warning that tells users NOT to check out v1.0.2 is allowed.
    """
    blocks = _readme_code_blocks(README.read_text(encoding="utf-8"))
    for body in blocks:
        assert "checkout v1.0.2" not in body, (
            "README Quick Start must not instruct `git checkout v1.0.2` for the "
            "root-compose install; that pre-fix release reintroduces the upstream "
            "app image. Use the default development branch until a newer stable "
            "release contains this fix."
        )
    assert any(
        "checkout claude/practical-wozniak-9s1t6z" in body for body in blocks
    ), "README local Quick Start should check out the default development branch."


def test_prod_compose_builds_from_source():
    text = PROD_COMPOSE.read_text(encoding="utf-8")
    assert re.search(r"^\s*build:", text, re.MULTILINE), (
        "deploy/docker-compose.prod.yml must build ChatBot 5400 from source."
    )
    assert not UPSTREAM_APP_IMAGE.search(text), (
        "deploy/docker-compose.prod.yml must not run the upstream app image."
    )
