from typing import ClassVar, List, Literal, Optional

from pydantic import Field

from open_notebook.domain.base import RecordModel


class ContentSettings(RecordModel):
    record_id: ClassVar[str] = "open_notebook:content_settings"
    default_content_processing_engine_doc: Optional[
        Literal["auto", "docling", "simple"]
    ] = Field(
        "docling",
        description=(
            "Default Content Processing Engine for Documents. 'docling' preserves "
            "structure (headings, multi-level lists like Điều/Khoản) in .docx/.pdf; "
            "it falls back to 'auto' automatically when the docling runtime is not "
            "installed."
        ),
    )
    default_content_processing_engine_url: Optional[
        Literal["auto", "firecrawl", "jina", "crawl4ai", "simple"]
    ] = Field("auto", description="Default Content Processing Engine for URLs")
    default_embedding_option: Optional[Literal["ask", "always", "never"]] = Field(
        "ask", description="Default Embedding Option for Vector Search"
    )
    auto_delete_files: Optional[Literal["yes", "no"]] = Field(
        "yes", description="Auto Delete Uploaded Files"
    )
    docling_ocr: Optional[bool] = Field(
        True,
        description=(
            "Run OCR on scanned PDFs and images when the Docling engine handles "
            "them. Disable for faster processing of text-native documents."
        ),
    )
    # --- OCR Engine Manager (docs/ocr) -------------------------------------
    # Defaults reproduce the pre-existing behaviour exactly (RapidOCR as picked
    # by Docling's Auto mode, Docling's default threads, no forced full-page
    # OCR), so existing records without these fields need no migration.
    # The engine is changed only through POST /api/ocr/engines/{id}/activate,
    # which refuses engines that are not ready.
    docling_ocr_engine: Optional[
        Literal["rapidocr", "tesseract_fast", "tesseract_best", "easyocr"]
    ] = Field(
        "rapidocr",
        description="OCR engine Docling uses for scanned PDFs and images.",
    )
    docling_ocr_device: Optional[Literal["cpu"]] = Field(
        "cpu",
        description="OCR runs on CPU only (informational; layout/table devices are unchanged).",
    )
    docling_ocr_num_threads: Optional[int] = Field(
        None,
        ge=1,
        le=64,
        description="CPU threads for the Docling pipeline; None keeps Docling's default (4).",
    )
    docling_ocr_force_full_page: Optional[bool] = Field(
        False,
        description="OCR the whole page even where the PDF has a text layer.",
    )
    docling_formulas: Optional[bool] = Field(
        False,
        description=(
            "Extract mathematical formulas as structured markup when the Docling "
            "engine handles a document. Adds processing time."
        ),
    )
    docling_vision: Optional[bool] = Field(
        False,
        description=(
            "Describe images and charts using a vision model when the Docling "
            "engine handles a document. Significantly slower and may invoke a "
            "vision model."
        ),
    )
    youtube_preferred_languages: Optional[List[str]] = Field(
        ["en", "pt", "es", "de", "nl", "en-GB", "fr", "hi", "ja", "zh-CN", "zh-TW"],
        description="Preferred languages for YouTube transcripts",
    )
    podcast_enabled: Optional[bool] = Field(
        True,
        description=(
            "Whether the Podcast feature is available to users. When False, the "
            "Podcast navigation entry, the 'Create podcast' action and the podcast "
            "quick-action (Ctrl+K) are hidden app-wide. Toggled by an admin in "
            "Settings. Defaults to True so existing deployments are unaffected."
        ),
    )
