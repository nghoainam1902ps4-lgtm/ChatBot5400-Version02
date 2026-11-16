"""Automatic full-page OCR for scans under tilted visible text boxes (D-33).

Docling 2.129 drops every OCR cell whose box touches the axis-aligned box of a
VISIBLE PDF text cell; one diagonal watermark line therefore wipes out most of
a scanned page. ``pdf_prep`` measures that situation and, when the opt-in flag
is set, the document is converted in Docling's official full-page OCR mode.

Every PDF here is synthetic and written by ``scripts/ocr/generate_overlay_fixtures``
(no real document, neutral watermark text). Real-pipeline checks live in
``tests/test_ocr_auto_full_page_pipeline.py``.
"""

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ocr"))

pytest.importorskip("pypdfium2")
Image = pytest.importorskip("PIL.Image")

import generate_overlay_fixtures as fx  # noqa: E402

from open_notebook.ocr import docling_extract, pdf_prep  # noqa: E402
from open_notebook.ocr.options import OcrSettings  # noqa: E402

FLAG = pdf_prep.AUTO_FULL_PAGE_ENV
BODY = (
    "Dieu 1. Pham vi dieu chinh. Quy dinh nay quy dinh ve dieu kien vay von, "
    "han muc, lai suat va thoi han cho vay doi voi khach hang. " * 12
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in (
        FLAG,
        pdf_prep.OVERLAY_MIN_ANGLE_ENV,
        pdf_prep.OVERLAY_MIN_COVERAGE_ENV,
        pdf_prep.OVERLAY_TEXT_PAGE_CHARS_ENV,
        pdf_prep.DISABLE_ENV,
    ):
        monkeypatch.delenv(var, raising=False)
    pdf_prep._overlay_scan_cached.cache_clear()
    yield
    pdf_prep._overlay_scan_cached.cache_clear()


def _scan(size=fx.A4, share=1.0) -> fx.Page:
    """A page whose image covers ``share`` of it (blank: geometry tests only)."""
    img = Image.new("L", (124, 175), 255)
    w, h = size
    rect = None if share >= 1.0 else (0.0, h * (1 - share), w, h)
    return fx.scan_page(img, size=size, rect=rect)


def _with(page: fx.Page, *groups) -> fx.Page:
    for g in groups:
        page.texts.extend(g if isinstance(g, list) else [g])
    return page


def _hidden():
    return fx.text_lines(BODY, size=11, invisible=True)


def _digital():
    return fx.text_lines(BODY, size=11)


def _write(tmp_path, pages, name="doc.pdf") -> str:
    path = tmp_path / name
    path.write_bytes(fx.build_pdf(pages if isinstance(pages, list) else [pages]))
    return str(path)


def _reported_structure():
    """Full-page scan + hidden OCR layer + one visible 55 degree watermark."""
    return _with(_scan(), _hidden(), fx.watermark(55))


# --- what is measured ---------------------------------------------------------------


class TestMeasurements:
    def test_the_reported_structure(self, tmp_path):
        scan = pdf_prep.overlay_scan(_write(tmp_path, _reported_structure()))
        assert scan.status == "ok" and scan.pages == 1 and scan.scan_pages == 1
        page = scan.details[0]
        assert page.image_share == pytest.approx(1.0, abs=0.01)
        assert page.visible_objects == 1 and page.invisible_objects > 10
        assert page.tilted_boxes == 1 and page.angles == (35,)  # 55 from the x axis
        assert page.max_inflation > 5  # the box is far larger than its characters
        assert page.invisible_chars > 500  # the hidden layer is counted apart
        # One tilted line claims most of the page ...
        assert page.conflict_share > 0.8 and page.max_box_share > 0.8
        # ... while the hidden OCR layer is not counted as visible text.
        assert page.ordinary_chars == 0
        assert page.at_risk() and scan.risk_pages == [1]
        assert scan.decision == "full_page"

    def test_hidden_layer_and_ordinary_text_are_told_apart(self, tmp_path):
        page = _with(
            _scan(),
            _hidden(),
            fx.watermark(55),
            fx.header_footer(),
            fx.signature_block(),
        )
        info = pdf_prep.overlay_scan(_write(tmp_path, page)).details[0]
        assert info.visible_objects == 6  # watermark + 2 header/footer + 3 signature
        assert info.tilted_boxes == 1
        assert 50 < info.ordinary_chars < 200  # header, footer, signature only
        assert info.at_risk()

    @pytest.mark.parametrize("in_form", [False, True])
    def test_watermark_inside_a_form_xobject_is_measured_in_page_space(
        self, tmp_path, in_form
    ):
        page = _with(_scan(), fx.watermark(55, in_form=in_form))
        info = pdf_prep.overlay_scan(_write(tmp_path, page)).details[0]
        assert info.tilted_boxes == 1 and info.angles == (35,)
        assert info.conflict_share > 0.8

    @pytest.mark.parametrize(
        "angle,tilt", [(15, 15), (30, 30), (45, 45), (55, 35), (75, 15), (-45, 45)]
    )
    def test_tilt_is_the_distance_from_the_nearest_axis(self, tmp_path, angle, tilt):
        info = pdf_prep.overlay_scan(
            _write(tmp_path, _with(_scan(), fx.watermark(angle)))
        ).details[0]
        assert info.angles == (tilt,) and info.at_risk()

    def test_boxes_are_clipped_to_the_page(self, tmp_path):
        page = _with(_scan(), fx.watermark(55, repeat=30))  # far longer than the page
        info = pdf_prep.overlay_scan(_write(tmp_path, page)).details[0]
        assert info.max_box_share <= 1.0 and info.conflict_share <= 1.0

    def test_only_the_part_over_an_image_counts(self, tmp_path):
        """The image covers the top 60%: the box is only at risk where it overlaps."""
        full = pdf_prep.overlay_scan(
            _write(tmp_path, _with(_scan(), fx.watermark(55)), "full.pdf")
        ).details[0]
        part = pdf_prep.overlay_scan(
            _write(tmp_path, _with(_scan(share=0.6), fx.watermark(55)), "part.pdf")
        ).details[0]
        assert part.image_share == pytest.approx(0.6, abs=0.02)
        assert part.max_box_share == pytest.approx(full.max_box_share, abs=0.02)
        assert part.conflict_share < full.conflict_share * 0.75

    def test_other_page_sizes(self, tmp_path):
        for size in ((612.0, 792.0), (841.89, 595.28), (2384.0, 3370.0)):
            page = _with(
                _scan(size=size),
                fx.watermark(40, size=size[0] / 30, centre=(size[0] / 2, size[1] / 2)),
            )
            scan = pdf_prep.overlay_scan(_write(tmp_path, page, f"{int(size[0])}.pdf"))
            assert scan.decision == "full_page", size


# --- look-alikes that must not trigger ---------------------------------------------------


def _negatives():
    half = Image.new("L", (124, 96), 255)
    return {
        "plain scan": _scan(),
        "scan + hidden OCR layer": _with(_scan(), _hidden()),
        "scan + hidden layer + header / footer / signature": _with(
            _scan(), _hidden(), fx.header_footer(), fx.signature_block()
        ),
        "born-digital text": fx.Page(texts=_digital()),
        "born-digital text + diagonal watermark": fx.Page(
            texts=[*_digital(), fx.watermark(55)]
        ),
        "digital text over a background image + watermark": _with(
            _scan(), _digital(), fx.watermark(55)
        ),
        "scan with a VISIBLE ordinary text layer + watermark": _with(
            _scan(), _digital(), fx.watermark(55)
        ),
        "vertical (90 degree) margin text": _with(
            _scan(), _hidden(), fx.watermark(90, repeat=4, centre=(40, 420))
        ),
        "small diagonal stamp in a corner": _with(
            _scan(),
            _hidden(),
            fx.watermark(45, size=9, repeat=1, centre=(520, 60), text="BAN SAO"),
        ),
        "large horizontal watermark": _with(
            _scan(), _hidden(), fx.watermark(0, size=60, repeat=1, text="MAU NOI BO")
        ),
        "scan under a VISIBLE text layer tilted 2 degrees": _with(
            _scan(), fx.tilted(_digital(), 2)
        ),
        "digital text + half-page figure + watermark": _with(
            fx.scan_page(half, rect=(0, fx.A4[1] * 0.45, fx.A4[0], fx.A4[1])),
            fx.text_lines(BODY, size=11, top=350, max_lines=22),
            fx.watermark(55),
        ),
    }


@pytest.mark.parametrize("name", list(_negatives()))
def test_look_alikes_are_not_at_risk(tmp_path, name, monkeypatch):
    monkeypatch.setenv(FLAG, "true")
    path = _write(tmp_path, _negatives()[name])
    scan = pdf_prep.overlay_scan(path)
    assert scan.risk_pages == [] and scan.decision == "none", name
    decision = pdf_prep.decide_ocr_mode(path, True, False)
    assert not decision.triggered and decision.effective == "default"
    assert decision.reason == pdf_prep.REASON_NO_RISK


def test_axis_aligned_text_never_looks_tilted(tmp_path):
    """Horizontal and vertical text measures exactly its own cells, at any size."""
    page = _with(
        _scan(),
        fx.header_footer(),
        fx.signature_block(),
        fx.watermark(0, size=60, repeat=1, text="MAU NOI BO"),
        fx.watermark(90, repeat=4, centre=(40, 420)),
        fx.watermark(180, size=20, repeat=1),
        fx.watermark(270, size=30, repeat=1, centre=(550, 420)),
    )
    info = pdf_prep.overlay_scan(_write(tmp_path, page)).details[0]
    assert info.visible_objects == 9
    assert info.tilted_boxes == 0 and info.conflict_share == 0.0
    assert info.max_inflation == 0.0 and info.angles == ()


@pytest.mark.parametrize("angle", [2, 5, 10, 85, 88])
def test_a_slightly_tilted_long_line_is_a_tilted_box(tmp_path, angle):
    """Measured in Phase 10G: 2 degrees already costs 4% of the page text, 5
    degrees 11% — the box grows with the LENGTH of the line, not its angle."""
    info = pdf_prep.overlay_scan(
        _write(tmp_path, _with(_scan(), _hidden(), fx.watermark(angle)))
    ).details[0]
    assert info.tilted_boxes == 1 and info.max_inflation >= 3
    assert info.at_risk()


def test_visible_text_inside_the_box_is_not_claimed(tmp_path):
    """Where the PDF shows text of its own, keeping it is right: not counted."""
    alone = pdf_prep.overlay_scan(
        _write(tmp_path, _with(_scan(), fx.watermark(55)), "a.pdf")
    ).details[0]
    with_text = pdf_prep.overlay_scan(
        _write(tmp_path, _with(_scan(), _digital(), fx.watermark(55)), "b.pdf")
    ).details[0]
    assert with_text.max_box_share == alone.max_box_share
    assert with_text.conflict_share < alone.conflict_share - 0.1


@pytest.mark.parametrize("tilt", [1.5, 2, 3, 5, 8])
def test_a_visible_text_layer_that_follows_a_skewed_scan_is_text(tmp_path, tilt):
    """Tilted lines of text fill their own boxes. They are the text of the
    page, which Docling keeps; full-page OCR would read the scan through them."""
    scan = pdf_prep.overlay_scan(
        _write(tmp_path, _with(_scan(), fx.tilted(_digital(), tilt)))
    )
    info = scan.details[0]
    # Tilted boxes that claim enough of the page: the angle and coverage rules
    # alone would call this page at risk ...
    assert info.tilted_boxes > 5
    assert info.conflict_share >= pdf_prep.overlay_min_coverage()
    # ... but they hold more characters than empty space.
    assert info.filled_share > info.conflict_share
    assert info.text_chars() >= pdf_prep.overlay_text_page_chars()
    assert info.is_text_page() and not info.at_risk()
    assert scan.decision == "none"


@pytest.mark.parametrize("hidden", [True, False])
def test_a_watermark_with_many_characters_is_still_an_overlay(tmp_path, hidden):
    """Nine long tilted lines: as many characters as a text page, mostly empty boxes."""
    layers = [_hidden()] if hidden else []
    scan = pdf_prep.overlay_scan(
        _write(tmp_path, _with(_scan(), *layers, fx.paragraph_watermark(30)))
    )
    info = scan.details[0]
    assert info.tilted_chars >= pdf_prep.overlay_text_page_chars()
    assert info.conflict_share > 2 * info.filled_share
    assert info.text_chars() == 0 and not info.is_text_page()
    assert info.at_risk() and scan.decision == "full_page"


def test_the_reported_structure_is_mostly_empty_box(tmp_path):
    info = pdf_prep.overlay_scan(_write(tmp_path, _reported_structure())).details[0]
    assert info.conflict_share > 10 * info.filled_share > 0


def test_tiled_small_watermarks_add_up(tmp_path):
    page = _with(_scan(), _hidden(), fx.tiled_watermark(45))
    info = pdf_prep.overlay_scan(_write(tmp_path, page)).details[0]
    assert info.tilted_boxes > 10
    assert info.max_box_share < 0.05  # each box is small ...
    assert info.conflict_share > 0.2 and info.at_risk()  # ... together they are not
    assert info.conflict_share > info.filled_share  # and more empty than filled


# --- documents ------------------------------------------------------------------------------


class TestDocuments:
    def test_every_page_at_risk(self, tmp_path):
        pages = [
            _with(_scan(), fx.watermark(55), fx.header_footer(i + 1)) for i in range(5)
        ]
        scan = pdf_prep.overlay_scan(_write(tmp_path, pages))
        assert scan.pages == 5 and scan.risk_pages == [1, 2, 3, 4, 5]
        assert scan.decision == "full_page"

    def test_scans_without_the_watermark_do_not_block(self, tmp_path):
        pages = [_scan(), _with(_scan(), fx.watermark(55)), _with(_scan(), _hidden())]
        scan = pdf_prep.overlay_scan(_write(tmp_path, pages))
        assert scan.risk_pages == [2] and scan.text_pages == []
        assert scan.decision == "full_page"

    @pytest.mark.parametrize("digital_first", [True, False])
    def test_mixed_document_keeps_its_mode(self, tmp_path, monkeypatch, digital_first):
        monkeypatch.setenv(FLAG, "true")
        risky = [_reported_structure(), _reported_structure()]
        digital = [fx.Page(texts=_digital())]
        pages = digital + risky if digital_first else risky + digital
        path = _write(tmp_path, pages)
        scan = pdf_prep.overlay_scan(path)
        assert len(scan.risk_pages) == 2 and len(scan.text_pages) == 1
        assert scan.decision == "mixed"
        decision = pdf_prep.decide_ocr_mode(path, True, False)
        assert not decision.triggered and decision.effective == "default"
        assert decision.reason == pdf_prep.REASON_MIXED

    def test_a_digital_page_with_few_characters_is_not_a_text_page(self, tmp_path):
        cover = fx.Page(texts=[fx.Text("PHU LUC 01", 220, 500, size=20)])
        scan = pdf_prep.overlay_scan(_write(tmp_path, [cover, _reported_structure()]))
        assert scan.text_pages == [] and scan.decision == "full_page"

    def test_digital_pages_are_only_read_when_a_page_is_at_risk(
        self, tmp_path, monkeypatch
    ):
        """A born-digital document costs one object pass per page, no more."""
        calls = []
        real = pdf_prep._page_overlay

        def spy(page, number, count_text, deadline=None):
            calls.append((number, count_text))
            return real(page, number, count_text, deadline)

        monkeypatch.setattr(pdf_prep, "_page_overlay", spy)
        digital = [fx.Page(texts=_digital()) for _ in range(4)]
        pdf_prep.overlay_scan(_write(tmp_path, digital, "digital.pdf"))
        assert calls == [(1, False), (2, False), (3, False), (4, False)]
        calls.clear()
        pdf_prep.overlay_scan(
            _write(tmp_path, [_reported_structure(), *digital], "m.pdf")
        )
        # ... and with a page at risk the search stops at the first text page.
        assert calls[-1] == (2, True) and len(calls) == 6


# --- page frames: /Rotate and page boxes that do not start at (0, 0) ------------------------------


def _reframe(tmp_path, source: str, name: str, rotate: int = 0, box=None) -> str:
    """Save ``source`` with /Rotate and / or another MediaBox on every page."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(source)
    for page in pdf:
        if box is not None:
            page.set_mediabox(*box)
        if rotate:
            page.set_rotation(rotate)
    target = tmp_path / name
    pdf.save(str(target))
    pdf.close()
    return str(target)


class TestPageFrames:
    """Boxes are measured in the page's own user space (Phase 10H review)."""

    @pytest.mark.parametrize("rotate", [90, 180, 270])
    def test_a_rotated_page_measures_like_the_unrotated_one(self, tmp_path, rotate):
        plain = _write(tmp_path, _reported_structure(), "plain.pdf")
        turned = _reframe(tmp_path, plain, f"r{rotate}.pdf", rotate=rotate)
        a = pdf_prep.overlay_scan(plain).details[0]
        b = pdf_prep.overlay_scan(turned).details[0]
        assert b.image_share == a.image_share == 1.0
        assert (b.conflict_share, b.max_box_share, b.filled_share) == (
            a.conflict_share,
            a.max_box_share,
            a.filled_share,
        )
        assert b.at_risk() and pdf_prep.overlay_scan(turned).decision == "full_page"

    @pytest.mark.parametrize("rotate", [0, 90, 270])
    def test_a_tilted_stamp_near_the_top_edge_is_seen_on_a_rotated_page(
        self, tmp_path, rotate
    ):
        """It lies beyond the swapped height: the old frame cut it off."""
        stamp = fx.watermark(30, size=14, repeat=2, centre=(300, 770))
        plain = _write(tmp_path, _with(_scan(), _hidden(), stamp), "s.pdf")
        path = _reframe(tmp_path, plain, f"s{rotate}.pdf", rotate=rotate)
        info = pdf_prep.overlay_scan(path).details[0]
        reference = pdf_prep.overlay_scan(plain).details[0]
        assert info.conflict_share == reference.conflict_share > 0.02
        assert info.at_risk()

    def test_a_page_box_that_does_not_start_at_the_origin(self, tmp_path):
        tall = (595.0, 1442.0)
        page = fx.scan_page(
            Image.new("L", (124, 175), 255), size=tall, rect=(0, 600, 595, 1442)
        )
        page.texts.append(fx.watermark(55, centre=(297.5, 1021.0)))
        whole = _write(tmp_path, page, "whole.pdf")
        cropped = _reframe(tmp_path, whole, "cropped.pdf", box=(0, 600, 595, 1442))
        info = pdf_prep.overlay_scan(cropped).details[0]
        assert info.image_share == 1.0 and info.is_scan()
        reference = pdf_prep.overlay_scan(
            _write(tmp_path, _with(_scan(), fx.watermark(55)), "a4.pdf")
        ).details[0]
        assert info.conflict_share == pytest.approx(reference.conflict_share, abs=0.01)
        assert info.at_risk()

    def test_rotated_ordinary_documents_stay_ordinary(self, tmp_path):
        for name, page in (
            ("scan", _with(_scan(), _hidden())),
            ("text", fx.Page(texts=_digital())),
            ("header", _with(_scan(), _hidden(), fx.header_footer())),
        ):
            plain = _write(tmp_path, page, f"{name}.pdf")
            for rotate in (90, 270):
                path = _reframe(tmp_path, plain, f"{name}{rotate}.pdf", rotate=rotate)
                scan = pdf_prep.overlay_scan(path)
                assert scan.decision == "none" and scan.status == "ok", (name, rotate)


# --- bounds on what is read from an untrusted upload ---------------------------------------------


class TestBounds:
    """Past a bound the check gives up; the document keeps its configured mode."""

    def _stopped(self, monkeypatch, path, **limits):
        from loguru import logger

        for name, value in limits.items():
            monkeypatch.setattr(pdf_prep, name, value)
        monkeypatch.setenv(FLAG, "true")
        pdf_prep._overlay_scan_cached.cache_clear()
        messages = []
        sink = logger.add(lambda m: messages.append(m.record["message"]), level="DEBUG")
        try:
            scan = pdf_prep.overlay_scan(path)
            decision = pdf_prep.decide_ocr_mode(path, True, False)
        finally:
            logger.remove(sink)
        assert scan.status == "error" and scan.decision == "none"
        assert decision.reason == pdf_prep.REASON_CHECK_FAILED
        assert not decision.triggered and decision.effective == "default"
        stopped = [m for m in messages if m.startswith("OCR overlay check stopped")]
        assert len(stopped) == 1  # the second question is answered from the cache
        assert str(Path(path).parent) not in stopped[0] and "doc.pdf" not in stopped[0]
        return stopped[0]

    def test_too_many_pages(self, tmp_path, monkeypatch):
        path = _write(tmp_path, [_reported_structure() for _ in range(4)])
        assert "pages" in self._stopped(monkeypatch, path, OVERLAY_MAX_PAGES=3)

    def test_too_many_characters_on_a_page(self, tmp_path, monkeypatch):
        path = _write(tmp_path, _with(_scan(), _digital(), fx.watermark(55)))
        message = self._stopped(monkeypatch, path, OVERLAY_MAX_PAGE_CHARS=200)
        assert "characters" in message

    def test_too_many_objects_on_a_page(self, tmp_path, monkeypatch):
        path = _write(tmp_path, _with(_scan(), _hidden(), fx.tiled_watermark(45)))
        assert "objects" in self._stopped(
            monkeypatch, path, OVERLAY_MAX_PAGE_OBJECTS=10
        )

    def test_out_of_time(self, tmp_path, monkeypatch):
        path = _write(tmp_path, [_reported_structure() for _ in range(3)])
        assert " s" in self._stopped(monkeypatch, path, OVERLAY_BUDGET_SECONDS=-1.0)

    def test_the_default_bounds_do_not_touch_ordinary_documents(self, tmp_path):
        pages = [_reported_structure() for _ in range(40)]
        scan = pdf_prep.overlay_scan(_write(tmp_path, pages, "forty.pdf"))
        assert scan.status == "ok" and len(scan.risk_pages) == 40
        assert pdf_prep.OVERLAY_MAX_PAGES >= 1000
        assert pdf_prep.OVERLAY_MAX_PAGE_CHARS >= 50_000
        assert pdf_prep.OVERLAY_BUDGET_SECONDS >= 10

    def test_a_page_count_lie_is_not_walked(self, tmp_path, monkeypatch):
        """/Count far beyond the real pages: stopped before the first page."""
        data = fx.build_pdf([_reported_structure()])
        assert data.count(b"/Count 1") == 1
        lied = tmp_path / "count.pdf"
        lied.write_bytes(data.replace(b"/Count 1", b"/Count 999999", 1))
        calls = []
        real = pdf_prep._page_overlay
        monkeypatch.setattr(
            pdf_prep,
            "_page_overlay",
            lambda *a, **k: calls.append(1) or real(*a, **k),
        )
        scan = pdf_prep.overlay_scan(str(lied))
        assert scan.status == "error" and calls == []

    def test_unreadable_pages_are_reported_a_few_times_then_summed(
        self, tmp_path, monkeypatch
    ):
        from loguru import logger

        def broken(*args, **kwargs):
            raise RuntimeError("page cannot be read")

        monkeypatch.setattr(pdf_prep, "_page_overlay", broken)
        path = _write(tmp_path, [_reported_structure() for _ in range(12)])
        messages = []
        sink = logger.add(lambda m: messages.append(m.record["message"]), level="DEBUG")
        try:
            scan = pdf_prep.overlay_scan(path)
        finally:
            logger.remove(sink)
        assert scan.status == "ok" and scan.decision == "none"
        one_by_one = [m for m in messages if "skipped page" in m]
        assert len(one_by_one) == 3
        assert any("12 unreadable pages" in m for m in messages)

    @pytest.mark.parametrize("raw", ["2", "abc", "-1", "nan"])
    def test_an_ignored_threshold_is_reported_once(self, monkeypatch, raw):
        from loguru import logger

        monkeypatch.setattr(pdf_prep, "_ignored_env_values", set())
        monkeypatch.setenv(pdf_prep.OVERLAY_MIN_COVERAGE_ENV, raw)
        messages = []
        sink = logger.add(lambda m: messages.append(m.record["message"]), level="DEBUG")
        try:
            values = {pdf_prep.overlay_min_coverage() for _ in range(5)}
        finally:
            logger.remove(sink)
        assert values == {pdf_prep.DEFAULT_OVERLAY_MIN_COVERAGE}
        assert len([m for m in messages if "using the default" in m]) == 1


# --- thresholds --------------------------------------------------------------------------------


class TestThresholds:
    def test_defaults(self):
        assert pdf_prep.overlay_min_angle() == pdf_prep.DEFAULT_OVERLAY_MIN_ANGLE_DEG
        assert pdf_prep.overlay_min_coverage() == pdf_prep.DEFAULT_OVERLAY_MIN_COVERAGE
        assert (
            pdf_prep.overlay_text_page_chars()
            == pdf_prep.DEFAULT_OVERLAY_TEXT_PAGE_CHARS
        )

    @pytest.mark.parametrize("raw", ["", "abc", "nan", "inf", "-1", "0", "9999999999"])
    def test_nonsense_values_fall_back(self, monkeypatch, raw):
        for env in (
            pdf_prep.OVERLAY_MIN_ANGLE_ENV,
            pdf_prep.OVERLAY_MIN_COVERAGE_ENV,
            pdf_prep.OVERLAY_TEXT_PAGE_CHARS_ENV,
        ):
            monkeypatch.setenv(env, raw)
        self.test_defaults()

    def test_angle_threshold(self, tmp_path, monkeypatch):
        path = _write(tmp_path, _with(_scan(), fx.watermark(5)))
        assert pdf_prep.overlay_scan(path).decision == "full_page"
        monkeypatch.setenv(pdf_prep.OVERLAY_MIN_ANGLE_ENV, "10")
        scan = pdf_prep.overlay_scan(path)  # only clearly diagonal text now
        assert scan.decision == "none" and scan.details[0].tilted_boxes == 0

    def test_coverage_threshold(self, tmp_path, monkeypatch):
        """Calibrated in Phase 10G: 1.1% of the page cost 3% of the text (kept as
        it is), 3.0% cost 8% (switched to full-page OCR)."""
        short = _write(
            tmp_path, _with(_scan(), fx.watermark(55, size=10, repeat=1)), "s.pdf"
        )
        longer = _write(
            tmp_path, _with(_scan(), fx.watermark(55, size=16, repeat=1)), "l.pdf"
        )
        low = pdf_prep.overlay_scan(short).details[0].conflict_share
        high = pdf_prep.overlay_scan(longer).details[0].conflict_share
        assert 0.005 < low < pdf_prep.DEFAULT_OVERLAY_MIN_COVERAGE < high < 0.05
        assert pdf_prep.overlay_scan(short).decision == "none"
        assert pdf_prep.overlay_scan(longer).decision == "full_page"
        monkeypatch.setenv(pdf_prep.OVERLAY_MIN_COVERAGE_ENV, "0.005")
        assert pdf_prep.overlay_scan(short).decision == "full_page"
        monkeypatch.setenv(pdf_prep.OVERLAY_MIN_COVERAGE_ENV, "0.10")
        assert pdf_prep.overlay_scan(longer).decision == "none"

    def test_text_page_threshold(self, tmp_path, monkeypatch):
        page = _with(
            _scan(), fx.watermark(55), fx.header_footer(), fx.signature_block()
        )
        path = _write(tmp_path, page)
        assert pdf_prep.overlay_scan(path).decision == "full_page"
        monkeypatch.setenv(pdf_prep.OVERLAY_TEXT_PAGE_CHARS_ENV, "50")
        scan = pdf_prep.overlay_scan(path)  # now the header counts as page content
        assert scan.risk_pages == [] and scan.decision == "none"

    def test_a_hidden_layer_larger_than_the_visible_text_means_a_scan(
        self, tmp_path, monkeypatch
    ):
        """Evidence from the hidden OCR layer: the page content is in the image."""
        monkeypatch.setenv(pdf_prep.OVERLAY_TEXT_PAGE_CHARS_ENV, "50")
        page = _with(
            _scan(),
            _hidden(),
            fx.watermark(55),
            fx.header_footer(),
            fx.signature_block(),
        )
        info = pdf_prep.overlay_scan(_write(tmp_path, page)).details[0]
        assert 50 < info.ordinary_chars < info.invisible_chars
        assert not info.is_text_page() and info.at_risk()


# --- the decision ------------------------------------------------------------------------------


class TestDecision:
    def test_flag_is_off_by_default_and_nothing_is_read(self, tmp_path, monkeypatch):
        path = _write(tmp_path, _reported_structure())
        monkeypatch.setattr(
            pdf_prep, "overlay_scan", lambda p: pytest.fail("must not be analysed")
        )
        assert pdf_prep.auto_full_page_enabled() is False
        decision = pdf_prep.decide_ocr_mode(path, True, False)
        assert (decision.configured, decision.effective) == ("default", "default")
        assert not decision.triggered and decision.reason == pdf_prep.REASON_FLAG_OFF
        assert decision.as_meta() == {}  # metadata identical to earlier versions

    @pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes", "on"])
    def test_flag_values(self, monkeypatch, raw):
        monkeypatch.setenv(FLAG, raw)
        assert pdf_prep.auto_full_page_enabled() is True

    @pytest.mark.parametrize("raw", ["", "false", "0", "no", "off", "maybe"])
    def test_anything_else_keeps_it_off(self, monkeypatch, raw):
        monkeypatch.setenv(FLAG, raw)
        assert pdf_prep.auto_full_page_enabled() is False

    def test_triggered(self, tmp_path, monkeypatch):
        monkeypatch.setenv(FLAG, "true")
        decision = pdf_prep.decide_ocr_mode(
            _write(tmp_path, _reported_structure()), True, False
        )
        assert decision.triggered and decision.reason == pdf_prep.REASON_TILTED_TEXT
        assert (decision.configured, decision.effective) == ("default", "full_page")
        meta = decision.as_meta()
        assert meta["auto_full_page"] is True
        assert meta["ocr_mode_configured"] == "default"
        assert meta["ocr_mode_effective"] == "full_page"
        assert meta["auto_full_page_risk_pages"] == 1
        assert meta["auto_full_page_max_coverage"] > 0.8
        assert meta["auto_full_page_angles"] == [35]

    def test_ocr_switched_off_is_never_switched_on(self, tmp_path, monkeypatch):
        monkeypatch.setenv(FLAG, "true")
        monkeypatch.setattr(
            pdf_prep, "overlay_scan", lambda p: pytest.fail("must not be analysed")
        )
        decision = pdf_prep.decide_ocr_mode(
            _write(tmp_path, _reported_structure()), False, False
        )
        assert not decision.triggered and decision.effective == "default"
        assert decision.reason == pdf_prep.REASON_OCR_DISABLED

    def test_manual_force_full_page_is_kept(self, tmp_path, monkeypatch):
        monkeypatch.setenv(FLAG, "true")
        monkeypatch.setattr(
            pdf_prep, "overlay_scan", lambda p: pytest.fail("must not be analysed")
        )
        for path in (
            _write(tmp_path, _reported_structure(), "a.pdf"),
            _write(tmp_path, fx.Page(texts=_digital()), "b.pdf"),
        ):
            decision = pdf_prep.decide_ocr_mode(path, True, True)
            assert (decision.configured, decision.effective) == (
                "full_page",
                "full_page",
            )
            assert not decision.triggered and decision.reason == pdf_prep.REASON_MANUAL

    def test_other_files_and_failures_never_raise(self, tmp_path, monkeypatch):
        monkeypatch.setenv(FLAG, "true")
        png = tmp_path / "a.png"
        Image.new("L", (20, 20), 255).save(png)
        broken = tmp_path / "broken.pdf"
        broken.write_bytes(b"%PDF-1.4\nnot really a pdf")
        for path, reason in (
            (str(png), pdf_prep.REASON_NOT_A_PDF),
            (str(tmp_path / "missing.pdf"), pdf_prep.REASON_NOT_A_PDF),
            (str(broken), pdf_prep.REASON_CHECK_FAILED),
        ):
            decision = pdf_prep.decide_ocr_mode(path, True, False)
            assert not decision.triggered and decision.reason == reason
            assert decision.effective == "default"

    def test_a_failed_check_logs_no_file_name(self, tmp_path, monkeypatch):
        from loguru import logger

        monkeypatch.setenv(FLAG, "true")
        secret = tmp_path / "ten-tai-lieu-noi-bo.pdf"
        secret.write_bytes(b"%PDF-1.4\nnot really a pdf")

        def vanished(*args):
            raise FileNotFoundError(2, "No such file or directory", str(secret))

        vanished.cache_clear = lambda: None  # the autouse fixture clears the cache
        records = []
        sink = logger.add(lambda m: records.append(m.record["message"]), level="DEBUG")
        try:
            pdf_prep.decide_ocr_mode(str(secret), True, False)  # pdfium refuses it
            monkeypatch.setattr(pdf_prep, "_overlay_scan_cached", vanished)
            decision = pdf_prep.decide_ocr_mode(str(secret), True, False)
        finally:
            logger.remove(sink)
        assert decision.reason == pdf_prep.REASON_CHECK_FAILED
        assert len([m for m in records if "overlay check skipped" in m]) == 2
        assert not [m for m in records if "ten-tai-lieu" in m or str(tmp_path) in m]

    def test_the_file_is_never_modified(self, tmp_path, monkeypatch):
        monkeypatch.setenv(FLAG, "true")
        path = _write(tmp_path, _reported_structure())
        before = (
            hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            Path(path).stat().st_mtime_ns,
        )
        assert pdf_prep.decide_ocr_mode(path, True, False).triggered
        after = (
            hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            Path(path).stat().st_mtime_ns,
        )
        assert before == after
        assert sorted(p.name for p in tmp_path.iterdir()) == ["doc.pdf"]

    def test_analysis_is_cached_per_file_and_thresholds(self, tmp_path, monkeypatch):
        calls = []
        real = pdf_prep._overlay_scan
        monkeypatch.setattr(
            pdf_prep, "_overlay_scan", lambda p: calls.append(p) or real(p)
        )
        path = _write(tmp_path, _reported_structure())
        pdf_prep.overlay_scan(path)
        pdf_prep.overlay_scan(path)
        assert len(calls) == 1
        monkeypatch.setenv(pdf_prep.OVERLAY_MIN_COVERAGE_ENV, "0.5")
        pdf_prep.overlay_scan(path)
        assert len(calls) == 2  # other thresholds: measured again
        Path(path).write_bytes(fx.build_pdf([_scan()]))
        assert pdf_prep.overlay_scan(path).decision == "none"
        assert len(calls) == 3  # other content: measured again

    def test_log_line_has_the_required_fields_and_no_content(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(FLAG, "true")
        path = _write(tmp_path, _reported_structure(), "ten-tai-lieu-noi-bo.pdf")
        line = pdf_prep.decide_ocr_mode(path, True, False).describe("tesseract_agri")
        for part in (
            "engine=tesseract_agri",
            "configured=default",
            "effective=full_page",
            "auto_full_page=True",
            f"reason={pdf_prep.REASON_TILTED_TEXT}",
            "risk_pages=1",
            "pages=1",
            "max_coverage=",
            "max_box=",
            "max_inflation=",
            "angles=[35]",
            "thresholds:",
        ):
            assert part in line, part
        assert "ten-tai-lieu" not in line and fx.WATERMARK not in line
        assert "MAU" not in line and str(tmp_path) not in line

    def test_the_rule_reads_geometry_and_counts_only(self):
        """No organisation name and no watermark text can be hard-coded: the code
        that measures a page never reads what its text says."""
        source = Path(pdf_prep.__file__).read_text(encoding="utf-8").lower()
        body = source.split("def _page_overlay", 1)[1].split("def _overlay_scan", 1)[0]
        assert "fpdftext_gettext(" not in body and "get_text_range" not in body
        assert "fpdftextobj_gettext(" not in body
        # The one character-level read only tells ink from white space.
        assert body.count("fpdftext_getunicode(") == 1
        assert "fpdftext_getunicode(raw_page, i) > 32" in body

    @pytest.mark.parametrize(
        "text", ["AAAA BBBB 0000   " * 6, "zz yy xx ww vv   " * 6, "0123456789 " * 9]
    )
    def test_the_decision_does_not_depend_on_what_the_overlay_says(
        self, tmp_path, monkeypatch, text
    ):
        monkeypatch.setenv(FLAG, "true")
        path = _write(tmp_path, _with(_scan(), _hidden(), fx.watermark(55, text=text)))
        decision = pdf_prep.decide_ocr_mode(path, True, False)
        assert decision.triggered and decision.reason == pdf_prep.REASON_TILTED_TEXT


# --- conversion ---------------------------------------------------------------------------------


@pytest.fixture
def fake_converter(monkeypatch):
    seen = {}

    class Conv:
        def convert(self, path):
            seen["path"] = path
            return "result"

    def fake_build(cc, ocr, scale=None):
        seen["ocr"] = ocr
        return Conv()

    monkeypatch.setattr(docling_extract, "build_converter", fake_build)
    return seen


class TestConversion:
    def test_document_at_risk_is_converted_in_full_page_mode(
        self, tmp_path, monkeypatch, fake_converter
    ):
        monkeypatch.setenv(FLAG, "true")
        path = _write(tmp_path, _reported_structure())
        saved = OcrSettings(engine="tesseract_best")
        _, _, prep = docling_extract.convert_document(path, object(), saved)
        assert fake_converter["ocr"].force_full_page is True
        assert fake_converter["ocr"] == replace(saved, force_full_page=True)
        assert saved.force_full_page is False  # the saved choice is not touched
        assert fake_converter["path"] == path  # the original file, unchanged
        meta = prep.as_meta()
        assert meta["auto_full_page"] is True
        assert meta["auto_full_page_reason"] == pdf_prep.REASON_TILTED_TEXT
        assert meta["ocr_mode_effective"] == "full_page"

    @pytest.mark.parametrize(
        "engine",
        ["rapidocr", "tesseract_fast", "tesseract_best", "easyocr", "tesseract_agri"],
    )
    def test_every_engine(self, tmp_path, monkeypatch, fake_converter, engine):
        monkeypatch.setenv(FLAG, "true")
        path = _write(tmp_path, _reported_structure())
        ocr = OcrSettings(
            engine=engine, custom_version="v1" if "agri" in engine else None
        )
        docling_extract.convert_document(path, object(), ocr)
        assert fake_converter["ocr"].force_full_page is True
        assert fake_converter["ocr"].engine == engine
        assert fake_converter["ocr"].custom_version == ocr.custom_version

    def test_flag_off_restores_the_previous_behaviour(
        self, tmp_path, monkeypatch, fake_converter
    ):
        path = _write(tmp_path, _reported_structure())
        saved = OcrSettings(engine="tesseract_best")
        _, _, prep = docling_extract.convert_document(path, object(), saved)
        assert fake_converter["ocr"] == saved
        assert not any(
            k.startswith(("auto_full_page", "ocr_mode")) for k in prep.as_meta()
        )

    def test_ordinary_documents_are_converted_as_before(
        self, tmp_path, monkeypatch, fake_converter
    ):
        monkeypatch.setenv(FLAG, "true")
        saved = OcrSettings(engine="tesseract_best")
        for name, page in _negatives().items():
            path = _write(tmp_path, page, "n.pdf")
            _, _, prep = docling_extract.convert_document(path, object(), saved)
            assert fake_converter["ocr"] == saved, name
            assert prep.as_meta()["auto_full_page"] is False, name

    def test_manual_force_full_page_is_kept(
        self, tmp_path, monkeypatch, fake_converter
    ):
        monkeypatch.setenv(FLAG, "true")
        saved = OcrSettings(engine="tesseract_best", force_full_page=True)
        for page in (_reported_structure(), fx.Page(texts=_digital())):
            _, _, prep = docling_extract.convert_document(
                _write(tmp_path, page), object(), saved
            )
            assert fake_converter["ocr"] == saved
            meta = prep.as_meta()
            assert meta["auto_full_page"] is False
            assert meta["auto_full_page_reason"] == pdf_prep.REASON_MANUAL
            assert (
                meta["ocr_mode_configured"] == meta["ocr_mode_effective"] == "full_page"
            )

    def test_ocr_off_stays_off(self, tmp_path, monkeypatch, fake_converter):
        monkeypatch.setenv(FLAG, "true")
        monkeypatch.setattr(pdf_prep, "prepare", lambda *a: pytest.fail("must not run"))
        saved = OcrSettings(engine="tesseract_best", enabled=False)
        docling_extract.convert_document(
            _write(tmp_path, _reported_structure()), object(), saved
        )
        assert fake_converter["ocr"] == saved

    def test_mixed_document_is_left_alone_with_a_warning(
        self, tmp_path, monkeypatch, fake_converter
    ):
        from loguru import logger

        monkeypatch.setenv(FLAG, "true")
        records = []
        sink = logger.add(lambda m: records.append(m.record), level="INFO")
        try:
            path = _write(
                tmp_path,
                [fx.Page(texts=_digital()), _reported_structure()],
                "ho-so-mat.pdf",
            )
            saved = OcrSettings(engine="tesseract_agri", custom_version="v1")
            _, _, prep = docling_extract.convert_document(path, object(), saved)
        finally:
            logger.remove(sink)
        assert fake_converter["ocr"] == saved
        assert prep.as_meta()["auto_full_page_reason"] == pdf_prep.REASON_MIXED
        warnings = [r for r in records if r["level"].name == "WARNING"]
        assert len(warnings) == 1
        text = warnings[0]["message"]
        assert "reason=mixed_document" in text and "engine=tesseract_agri" in text
        assert "risk_pages=1" in text and "text_pages=1" in text
        assert "ho-so-mat" not in text

    def test_log_line_for_a_triggered_document(
        self, tmp_path, monkeypatch, fake_converter
    ):
        from loguru import logger

        monkeypatch.setenv(FLAG, "true")
        records = []
        sink = logger.add(lambda m: records.append(m.record["message"]), level="INFO")
        try:
            docling_extract.convert_document(
                _write(tmp_path, _reported_structure()),
                object(),
                OcrSettings(engine="rapidocr"),
            )
        finally:
            logger.remove(sink)
        lines = [m for m in records if m.startswith("OCR mode:")]
        assert len(lines) == 1
        assert "engine=rapidocr configured=default effective=full_page" in lines[0]
        assert "auto_full_page=True" in lines[0]

    @pytest.mark.parametrize("manual", [False, True])
    @pytest.mark.parametrize("enabled", [True, False])
    def test_flag_off_adds_no_log_line_and_no_metadata(
        self, tmp_path, fake_converter, monkeypatch, manual, enabled
    ):
        """Whatever the saved settings are: exactly the earlier behaviour."""
        from loguru import logger

        monkeypatch.setattr(
            pdf_prep, "overlay_scan", lambda p: pytest.fail("must not be analysed")
        )
        records = []
        sink = logger.add(lambda m: records.append(m.record["message"]), level="DEBUG")
        saved = OcrSettings(
            engine="tesseract_best", force_full_page=manual, enabled=enabled
        )
        try:
            _, _, prep = docling_extract.convert_document(
                _write(tmp_path, _reported_structure()), object(), saved
            )
        finally:
            logger.remove(sink)
        assert fake_converter["ocr"] == saved
        assert not [m for m in records if m.startswith("OCR mode:")]
        assert not any(
            k.startswith(("auto_full_page", "ocr_mode")) for k in prep.as_meta()
        )


# --- routing: the default RapidOCR path through content-core -------------------------------------


@pytest.fixture
def default_route(monkeypatch):
    """RapidOCR with default tuning: documents normally go to content-core."""
    from open_notebook.ocr import runtime

    monkeypatch.setattr(runtime, "auto_resolves_to_rapidocr", lambda: True)
    for var in ("OCR_RAPIDOCR_FORCE_CPU", "OCR_RAPIDOCR_PERSISTENT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(
        docling_extract, "_docling_routes", lambda mime, eng: eng == "docling"
    )
    assert docling_extract.native_path_required(OcrSettings()) is False


class TestDefaultRoute:
    @pytest.mark.asyncio
    async def test_flag_off_content_core_keeps_every_pdf(
        self, tmp_path, monkeypatch, default_route
    ):
        monkeypatch.setattr(
            pdf_prep, "overlay_scan", lambda p: pytest.fail("must not be analysed")
        )
        path = _write(tmp_path, _reported_structure())
        assert (
            await docling_extract.should_use_native_ocr(path, "docling", OcrSettings())
            is False
        )

    @pytest.mark.asyncio
    async def test_flag_on_the_document_at_risk_is_not_bypassed(
        self, tmp_path, monkeypatch, default_route
    ):
        monkeypatch.setenv(FLAG, "true")
        risky = _write(tmp_path, _reported_structure(), "risky.pdf")
        plain = _write(tmp_path, _with(_scan(), _hidden()), "plain.pdf")
        digital = _write(tmp_path, fx.Page(texts=_digital()), "digital.pdf")
        ocr = OcrSettings()
        assert (
            await docling_extract.should_use_native_ocr(risky, "docling", ocr) is True
        )
        assert (
            await docling_extract.should_use_native_ocr(plain, "docling", ocr) is False
        )
        assert (
            await docling_extract.should_use_native_ocr(digital, "docling", ocr)
            is False
        )
        # Not routed to Docling at all -> nothing to fix.
        assert (
            await docling_extract.should_use_native_ocr(risky, "simple", ocr) is False
        )

    @pytest.mark.asyncio
    async def test_ocr_off_and_mixed_documents_stay_on_content_core(
        self, tmp_path, monkeypatch, default_route
    ):
        monkeypatch.setenv(FLAG, "true")
        risky = _write(tmp_path, _reported_structure(), "risky.pdf")
        mixed = _write(
            tmp_path, [fx.Page(texts=_digital()), _reported_structure()], "mixed.pdf"
        )
        off = OcrSettings(enabled=False)
        assert (
            await docling_extract.should_use_native_ocr(risky, "docling", off) is False
        )
        assert (
            await docling_extract.should_use_native_ocr(mixed, "docling", OcrSettings())
            is False
        )

    @pytest.mark.asyncio
    async def test_source_graph_sends_the_document_to_the_ocr_layer(
        self, tmp_path, monkeypatch, default_route
    ):
        """End to end through content_process, RapidOCR left at its defaults."""
        from open_notebook.graphs import source as source_graph

        monkeypatch.setenv(FLAG, "true")
        calls = {"content_core": 0, "native": []}

        class Settings:
            youtube_preferred_languages = None
            default_content_processing_engine_url = None
            default_content_processing_engine_doc = "docling"
            docling_ocr = True
            docling_formulas = False
            docling_vision = False
            docling_ocr_engine = "rapidocr"
            docling_ocr_num_threads = None
            docling_ocr_force_full_page = False

        settings = Settings()

        async def get_instance():
            return settings

        class Out:
            title = "doc.pdf"
            content = "noi dung"

        async def fake_extract_content(**kw):
            calls["content_core"] += 1
            return Out()

        async def fake_native(path, cfg, ocr):
            calls["native"].append(ocr)
            return Out()

        class MM:
            async def get_defaults(self):
                class D:
                    default_speech_to_text_model = None

                return D()

        monkeypatch.setattr(source_graph.ContentSettings, "get_instance", get_instance)
        monkeypatch.setattr(
            source_graph.ContentSettings,
            "clear_instance",
            classmethod(lambda cls: None),
        )
        monkeypatch.setattr(source_graph, "_usable_engine", lambda e, k: e)
        monkeypatch.setattr(source_graph, "resolve_upload_path", lambda p: p)
        monkeypatch.setattr(source_graph, "ModelManager", MM)
        monkeypatch.setattr(source_graph, "extract_content", fake_extract_content)
        monkeypatch.setattr(source_graph, "extract_with_selected_ocr", fake_native)

        risky = _write(tmp_path, _reported_structure(), "risky.pdf")
        plain = _write(tmp_path, _with(_scan(), _hidden()), "plain.pdf")
        await source_graph.content_process({"content_state": {"file_path": plain}})
        assert calls == {"content_core": 1, "native": []}
        await source_graph.content_process({"content_state": {"file_path": risky}})
        assert calls["content_core"] == 1 and len(calls["native"]) == 1
        # The saved settings reach the OCR layer unchanged; the mode is decided there.
        assert calls["native"][0] == OcrSettings()
        assert settings.docling_ocr_force_full_page is False
        # Flag off: the same file goes back to content-core.
        monkeypatch.setenv(FLAG, "false")
        await source_graph.content_process({"content_state": {"file_path": risky}})
        assert calls["content_core"] == 2 and len(calls["native"]) == 1
