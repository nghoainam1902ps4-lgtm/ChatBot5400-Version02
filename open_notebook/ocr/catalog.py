"""The OCR engine catalog — the ONLY engines the OCR Engine Manager offers.

Exactly 3 engines / 4 choices (MASTER_PLAN §2). Every downloadable artifact is
pinned here by URL, size and SHA-256: the installer never accepts a URL from a
request, so there is no SSRF or "download anything" surface. Bumping a model
means editing this file (reviewed in Git), never a runtime input.

Checksums were computed from the official upstream artifacts:
- tessdata_fast / tessdata_best, tag 4.1.0 (github.com/tesseract-ocr)
- EasyOCR release assets pre-v1.1.6 (craft_mlt_25k) and v1.3 (latin_g2); the
  extracted .pth MD5s match the ones EasyOCR itself checks (easyocr/config.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EngineId = Literal["rapidocr", "tesseract_fast", "tesseract_best", "easyocr"]
ENGINE_IDS: tuple[str, ...] = (
    "rapidocr",
    "tesseract_fast",
    "tesseract_best",
    "easyocr",
)
DEFAULT_ENGINE: EngineId = "rapidocr"

RuntimeKind = Literal["builtin", "tesseract", "easyocr"]

TESSDATA_TAG = "4.1.0"
_TESS_FAST = (
    f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{TESSDATA_TAG}"
)
_TESS_BEST = (
    f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/{TESSDATA_TAG}"
)
_EASYOCR_REL = "https://github.com/JaidedAI/EasyOCR/releases/download"

# Hosts the installer may talk to (the catalog URLs and GitHub's release-asset
# redirect targets). Enforced on every redirect hop.
ALLOWED_DOWNLOAD_HOSTS = (
    "raw.githubusercontent.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
)

EASYOCR_PACKAGE = "easyocr"
EASYOCR_VERSION = "1.7.2"
EASYOCR_WHEEL_SHA256 = (
    "5be12f9b0e595d443c9c3d10b0542074b50f0ec2d98b141a109cd961fd1c177c"
)
TESSERACT_APT_PACKAGE = "tesseract-ocr"
TESSERACT_MIN_MAJOR = 4  # LSTM traineddata (tessdata_fast/best 4.x) needs >= 4


@dataclass(frozen=True)
class ModelFile:
    """One verified file inside the models directory."""

    rel_path: str  # relative to OCR_MODELS_DIR
    url: str
    sha256: str  # of the final file on disk
    size: int
    # When the upstream artifact is a zip, the single member to extract.
    archive_member: str | None = None
    archive_sha256: str | None = None
    archive_size: int | None = None
    # Shared between engines (never deleted while another engine needs it).
    shared: bool = False

    @property
    def download_size(self) -> int:
        return self.archive_size or self.size


@dataclass(frozen=True)
class EngineSpec:
    id: str
    display_name: str
    description: str
    languages: tuple[str, ...]  # human-readable
    docling_kind: str  # Docling OcrOptions.kind
    model_name: str
    model_version: str
    runtime: RuntimeKind
    license: str
    source_url: str
    files: tuple[ModelFile, ...] = field(default_factory=tuple)
    # Quality qualification (D-27): a statement about measured OCR quality for
    # Vietnamese business documents. Independent of "installed / ready" and of
    # "offline verified" — an engine can run offline and still not qualify.
    quality: str = "compatibility"

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def download_size(self) -> int:
        return sum(f.download_size for f in self.files)


_OSD = ModelFile(
    rel_path="tesseract/osd.traineddata",
    url=f"{_TESS_FAST}/osd.traineddata",
    sha256="9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff",
    size=10562727,
    shared=True,
)

# recommended   - measured best overall for Vietnamese text and tables
# speed         - faster Tesseract model; table labels weaker than "recommended"
# compatibility - the project's original engine, model and defaults unchanged
# experimental  - works, but did not meet the acceptance thresholds
QUALITY_TIERS = ("recommended", "speed", "compatibility", "experimental")

ENGINES: dict[str, EngineSpec] = {
    "rapidocr": EngineSpec(
        id="rapidocr",
        display_name="RapidOCR – PaddleOCR",
        description=(
            "Engine OCR gốc của dự án (Docling Auto → RapidOCR, PP-OCR mặc định). "
            "Giữ nguyên model và hành vi hiện tại."
        ),
        languages=("PP-OCR default (zh/en/Latin)",),
        docling_kind="rapidocr",
        model_name="PP-OCR default",
        model_version="bundled with rapidocr",
        runtime="builtin",
        license="Apache-2.0",
        source_url="https://github.com/RapidAI/RapidOCR",
    ),
    "tesseract_fast": EngineSpec(
        id="tesseract_fast",
        display_name="Tesseract Vietnamese Fast",
        description="Tesseract LSTM (tessdata_fast) tiếng Việt + tiếng Anh — ưu tiên tốc độ CPU.",
        languages=("vie", "eng"),
        docling_kind="tesseract",
        model_name="tessdata_fast",
        model_version=TESSDATA_TAG,
        runtime="tesseract",
        quality="speed",
        license="Apache-2.0",
        source_url="https://github.com/tesseract-ocr/tessdata_fast",
        files=(
            ModelFile(
                rel_path="tesseract/fast/vie.traineddata",
                url=f"{_TESS_FAST}/vie.traineddata",
                sha256="79df64caf7bcfb2a27df5042ecb6121e196eada34da774956995747636d5bfa1",
                size=531275,
            ),
            ModelFile(
                rel_path="tesseract/fast/eng.traineddata",
                url=f"{_TESS_FAST}/eng.traineddata",
                sha256="7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
                size=4113088,
            ),
            _OSD,
        ),
    ),
    "tesseract_best": EngineSpec(
        id="tesseract_best",
        display_name="Tesseract Vietnamese Best",
        description="Tesseract LSTM (tessdata_best) tiếng Việt + tiếng Anh — ưu tiên độ chính xác.",
        languages=("vie", "eng"),
        docling_kind="tesseract",
        model_name="tessdata_best",
        model_version=TESSDATA_TAG,
        runtime="tesseract",
        quality="recommended",
        license="Apache-2.0",
        source_url="https://github.com/tesseract-ocr/tessdata_best",
        files=(
            ModelFile(
                rel_path="tesseract/best/vie.traineddata",
                url=f"{_TESS_BEST}/vie.traineddata",
                sha256="b6b49293d95d0b6dbd8780174627e82c75be957b6f4ed9862155540d6b00bb45",
                size=12435550,
            ),
            ModelFile(
                rel_path="tesseract/best/eng.traineddata",
                url=f"{_TESS_BEST}/eng.traineddata",
                sha256="8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba",
                size=15400601,
            ),
            _OSD,
        ),
    ),
    "easyocr": EngineSpec(
        id="easyocr",
        display_name="EasyOCR Vietnamese",
        description="EasyOCR (CRAFT + Latin Gen2) tiếng Việt + tiếng Anh, chạy CPU.",
        languages=("vi", "en"),
        docling_kind="easyocr",
        model_name="craft_mlt_25k + latin_g2",
        model_version=f"easyocr {EASYOCR_VERSION}",
        runtime="easyocr",
        quality="experimental",
        license="Apache-2.0",
        source_url="https://github.com/JaidedAI/EasyOCR",
        files=(
            ModelFile(
                rel_path="easyocr/craft_mlt_25k.pth",
                url=f"{_EASYOCR_REL}/pre-v1.1.6/craft_mlt_25k.zip",
                sha256="4a5efbfb48b4081100544e75e1e2b57f8de3d84f213004b14b85fd4b3748db17",
                size=83152330,
                archive_member="craft_mlt_25k.pth",
                archive_sha256="8dc6a1c703a89ed56308ef742d26ebd45c656248cbbbda6e7fe60e569f873e65",
                archive_size=77251756,
            ),
            ModelFile(
                rel_path="easyocr/latin_g2.pth",
                url=f"{_EASYOCR_REL}/v1.3/latin_g2.zip",
                sha256="aaa95be1c4a9cb3496879bed7c520886ce1164f89e026f0c54488394e74e8c55",
                size=15406141,
                archive_member="latin_g2.pth",
                archive_sha256="29f1920c493378da65a59793fb70e7e190504662b6bed57ab26f4067eb5f3769",
                archive_size=14284936,
            ),
        ),
    ),
}

# Docling-native language codes per engine (D-04: Tesseract uses sub-directory
# stems under the shared TESSDATA_PREFIX).
DOCLING_LANGS: dict[str, list[str]] = {
    "rapidocr": [],  # [] == RapidOCR default model, exactly what Auto passes today
    "tesseract_fast": ["fast/vie", "fast/eng"],
    "tesseract_best": ["best/vie", "best/eng"],
    "easyocr": ["vi", "en"],
}


def get_engine(engine_id: str) -> EngineSpec:
    """Return the spec, or raise ValueError for anything outside the catalog."""
    spec = ENGINES.get(engine_id)
    if spec is None:
        raise ValueError(f"Unknown OCR engine: {engine_id!r}")
    return spec


def engines_sharing(rel_path: str) -> list[str]:
    return [
        e.id for e in ENGINES.values() if any(f.rel_path == rel_path for f in e.files)
    ]
