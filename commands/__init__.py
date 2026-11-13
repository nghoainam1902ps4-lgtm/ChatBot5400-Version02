"""Surreal-commands integration for Open Notebook"""

# The worker starts via `surreal-commands-worker --import-modules commands`,
# so this package is imported before the worker connects to SurrealDB. Inject
# the internal DB hosts into no_proxy first so the DB websocket is never
# tunnelled through a configured HTTP proxy (issue #1160).
from open_notebook.utils.proxy import ensure_internal_no_proxy

ensure_internal_no_proxy()

from .embedding_commands import (
    embed_insight_command,
    embed_note_command,
    embed_source_command,
    rebuild_embeddings_command,
)
from .ocr_commands import (
    ocr_check_readiness_command,
    ocr_install_model_command,
    ocr_prepare_engine_command,
    ocr_test_engine_command,
)
from .podcast_commands import generate_podcast_command
from .source_commands import process_source_command

__all__ = [
    # Embedding commands
    "embed_note_command",
    "embed_insight_command",
    "embed_source_command",
    "rebuild_embeddings_command",
    # Other commands
    "generate_podcast_command",
    "process_source_command",
    # OCR Engine Manager
    "ocr_install_model_command",
    "ocr_test_engine_command",
    "ocr_prepare_engine_command",
    "ocr_check_readiness_command",
]
