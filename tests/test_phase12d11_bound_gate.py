"""Synthetic provenance controls for the strict release comparison."""

import hashlib
import json

import pytest
from test_phase12d9_standard_gate import REGIONS, needs_ocr
from test_phase12d9_standard_gate import gate as rendered_ocr  # noqa: F401

from scripts.ocr import phase12_standard_diff as gate


@pytest.fixture
def evidence(tmp_path):
    path = tmp_path / "case.evidence"
    (path / "tesseract").mkdir(parents=True)
    identity = {"document": "case", "run_id": "a" * 32}
    models = {"vie": "b" * 64}
    elements, spans = [], []
    for page, offset in ((1, 0), (2, 8)):
        invocation = f"{page:04d}-001-{page:06d}"
        crop = f"{page:04d}_001_{page:06d}"
        raw = (
            gate._TSV_HEADER
            + gate._TSV_PARENTS
            + (
                "5\t1\t1\t1\t1\t1\t7\t7\t8\t9\t96\t12-\n"
                "5\t1\t1\t1\t1\t2\t22\t7\t8\t9\t96\tAB\n"
            )
        )
        (path / f"tesseract/{crop}.tsv").write_text(raw, encoding="utf-8")
        (path / f"tesseract/{crop}.json").write_text(
            json.dumps(
                {
                    **identity,
                    "invocation": invocation,
                    "page": page,
                    "region": 1,
                    "bbox": [0, 0, 50, 50],
                    "engine": "vie",
                    "model_files": [{"name": "vie", "sha256": models["vie"]}],
                }
            ),
            encoding="utf-8",
        )
        common = {
            **identity,
            "page": page,
            "cluster": page,
            "bbox": [0, 0, 50, 50],
            "text": "12- AB",
            "v120_text": "12AB",
        }
        elements.append(
            {
                **common,
                "cells": [
                    {
                        "invocation": invocation,
                        "row": 4,
                        "raw": "12-",
                        "text": "12-",
                        "bbox": [7, 7, 15, 16],
                    },
                    {
                        "invocation": invocation,
                        "row": 5,
                        "raw": "AB",
                        "text": "AB",
                        "bbox": [22, 7, 30, 16],
                    },
                ],
            }
        )
        spans.append(
            {
                **common,
                "item": f"#/texts/{page - 1}",
                "start": offset,
                "end": offset + 6,
                "hyphens": [
                    {
                        "invocation": invocation,
                        "row": 4,
                        "start": offset,
                        "end": offset + 3,
                    }
                ],
            }
        )
    return path, identity, models, elements, spans


def _verify(evidence, before="12AB\n\n12AB", after="12- AB\n\n12- AB"):
    path, identity, models, elements, spans = evidence
    for name, rows in (("elements", elements), ("output_spans", spans)):
        (path / f"{name}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
    files = {
        p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in path.rglob("*")
        if p.is_file()
    }
    return gate.verify_bound_output(
        before,
        after,
        path,
        {
            "name": identity["document"],
            "evidence_files": files,
            "ocr_model_files": models,
        },
        identity,
    )


def test_two_identical_tokens_are_proven_by_different_source_spans(evidence):
    report = _verify(evidence)
    assert report["class"] == gate.EXPECTED_HYPHEN
    assert report["hyphen_occurrence_status"] == "verified"


@pytest.mark.parametrize(
    "problem",
    ["run", "document", "page", "crop", "engine", "occurrence", "swap", "orientation"],
)
def test_unbound_evidence_is_not_verified(evidence, problem):
    path, _identity, _models, elements, spans = evidence
    if problem == "run":
        spans[0]["run_id"] = "b" * 32
    elif problem == "document":
        spans[0]["document"] = "another"
    elif problem == "page":
        spans[0]["page"] = 2
    elif problem == "crop":
        elements[0]["cells"][0]["bbox"] = [300, 10, 310, 18]
    elif problem == "engine":
        sidecar = next((path / "tesseract").glob("*.json"))
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        metadata["engine"] = "eng"
        sidecar.write_text(json.dumps(metadata), encoding="utf-8")
    elif problem == "occurrence":
        assert _verify(evidence, after="12- AB\n\n12AB")["class"] == gate.NOT_VERIFIED
        return
    elif problem == "swap":
        spans[0]["hyphens"][0]["invocation"], spans[1]["hyphens"][0]["invocation"] = (
            spans[1]["hyphens"][0]["invocation"],
            spans[0]["hyphens"][0]["invocation"],
        )
    else:
        (path / "orientation.jsonl").write_text('{"text":"12- AB"}', encoding="utf-8")
    assert _verify(evidence)["class"] == gate.NOT_VERIFIED


@needs_ocr
def test_actual_tesseract_and_docling_emit_verifiable_source_spans(rendered_ocr):  # noqa: F811
    rendered_ocr.pdf("synthetic", REGIONS)
    baseline = rendered_ocr.export_v120()
    candidate = rendered_ocr.export_candidate()
    folder = rendered_ocr.after / "synthetic.evidence"
    invocations = sorted((folder / "tesseract").glob("*.json"))
    assert invocations
    sidecar = json.loads(invocations[0].read_text(encoding="utf-8"))
    actual_models = {m["name"]: m["sha256"] for m in sidecar["model_files"]}
    assert actual_models and all(
        gate._digest(digest) for digest in actual_models.values()
    )
    candidate["documents"][0]["ocr_model_files"] = actual_models
    baseline["documents"][0]["ocr_model_files"] = actual_models
    baseline.update(
        commit="f2fdf2714a7c0b5b196132f71cfc091928befc06", image_id="sha256:" + "a" * 64
    )
    candidate.update(commit="a" * 40, image_id="sha256:" + "b" * 64)
    for root, manifest in (
        (rendered_ocr.before, baseline),
        (rendered_ocr.after, candidate),
    ):
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    code, report = rendered_ocr.diff(
        "--release",
        "--candidate-commit",
        candidate["commit"],
        "--candidate-image",
        candidate["image_id"],
    )
    assert code == 0, report
    assert report["documents"]["synthetic"]["hyphen_occurrence_status"] == "verified"
