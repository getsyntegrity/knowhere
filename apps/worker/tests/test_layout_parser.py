import os
from pathlib import Path

import pandas as pd


TEST_ENV_ROOT = Path(__file__).resolve().parent / ".tmp_layout_parser"
TEST_ENV_ROOT.mkdir(exist_ok=True)
(TEST_ENV_ROOT / "chromedriver").write_text("", encoding="utf-8")
(TEST_ENV_ROOT / "font.ttf").write_text("", encoding="utf-8")

os.environ.setdefault("DS_KEY", "test")
os.environ.setdefault("DS_URL", "https://example.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("S3_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "test-secret-key")
os.environ.setdefault("S3_TEMP_PATH", str(TEST_ENV_ROOT))
os.environ.setdefault("USERS_DATA_PATH", str(TEST_ENV_ROOT))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TMP_PATH", str(TEST_ENV_ROOT))
os.environ.setdefault("FONT_PATH", str(TEST_ENV_ROOT / "font.ttf"))
os.environ.setdefault("CHROMEDRIVER_PATH", str(TEST_ENV_ROOT / "chromedriver"))

from app.services.document_parser import layout_parser


def test_est_hierarchies_llm_strips_resource_rows_before_llm(monkeypatch):
    llm_input_ids = []

    def fake_hierarchy_llm(df, *args, **kwargs):
        llm_input_ids.extend(df["id"].tolist())
        return [{"id": 11, "level": 2}, {"id": 13, "level": -1}]

    monkeypatch.setattr(layout_parser, "hiearchy_llm", fake_hierarchy_llm)

    raw_preds = pd.DataFrame(
        [
            {"id": 10, "heading": "resource or annotation", "level": -1, "reason": "res"},
            {"id": 11, "heading": "1 Introduction", "level": 1, "reason": "intro"},
            {"id": 12, "heading": "resource or annotation", "level": -1, "reason": "res"},
            {"id": 13, "heading": "2 Background", "level": 1, "reason": "bg"},
        ]
    )

    result = layout_parser.est_hierarchies_llm(raw_preds, prompt_limt=1000)

    assert llm_input_ids == [11, 13]
    assert result["id"].tolist() == [10, 11, 12, 13]
    assert result["heading"].tolist() == [
        "resource or annotation",
        "1 Introduction",
        "resource or annotation",
        "2 Background",
    ]
    assert result["level"].tolist() == [-1, 2, -1, -1]


def test_est_hierarchies_llm_returns_resource_rows_when_no_candidates(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM should not be called when only resource rows remain")

    monkeypatch.setattr(layout_parser, "hiearchy_llm", fail_if_called)

    raw_preds = pd.DataFrame(
        [
            {"id": 3, "heading": "resource or annotation", "level": -1, "reason": "res-a"},
            {"id": 1, "heading": "resource or annotation", "level": -1, "reason": "res-b"},
        ]
    )

    result = layout_parser.est_hierarchies_llm(raw_preds, prompt_limt=1000)

    assert result["id"].tolist() == [1, 3]
    assert result["heading"].tolist() == ["resource or annotation", "resource or annotation"]
    assert result["level"].tolist() == [-1, -1]


def test_est_hierarchies_llm_restores_resource_rows_after_multi_chunk_mapping(monkeypatch):
    llm_input_ids = []

    def fake_hierarchy_llm(df, *args, **kwargs):
        llm_input_ids.extend(df["id"].tolist())
        return [{"id": 2, "level": 3}]

    def fake_handle_unseen_codes(df, level_dfs, lvl_mapping, output_dir=None):
        assert df["id"].tolist() == [2, 3]
        assert [chunk["id"].tolist() for chunk in level_dfs] == [[2], [3]]
        lvl_mapping["reason-b"] = {
            "lvls": [1],
            "positive_lvls": [1],
            "freqs": {1: 1},
            "mapped_lvl": 4,
        }
        return lvl_mapping

    monkeypatch.setattr(layout_parser, "hiearchy_llm", fake_hierarchy_llm)
    monkeypatch.setattr(layout_parser, "handle_unseen_codes", fake_handle_unseen_codes)

    heading_a = "2.1 This heading is intentionally long enough to force its own chunk"
    heading_b = "2.2 Another long heading that should stay untruncated in the final output"
    raw_preds = pd.DataFrame(
        [
            {"id": 1, "heading": "resource or annotation", "level": -1, "reason": "res"},
            {"id": 2, "heading": heading_a, "level": 1, "reason": "reason-a"},
            {"id": 3, "heading": heading_b, "level": 1, "reason": "reason-b"},
            {"id": 4, "heading": "resource or annotation", "level": -1, "reason": "res"},
        ]
    )

    result = layout_parser.est_hierarchies_llm(raw_preds, prompt_limt=6)

    assert llm_input_ids == [2]
    assert result["id"].tolist() == [1, 2, 3, 4]
    assert result["heading"].tolist() == [
        "resource or annotation",
        heading_a,
        heading_b,
        "resource or annotation",
    ]
    assert result["level"].tolist() == [-1, 3, 4, -1]


def test_est_hierarchies_llm_strips_markdown_markers_before_llm(monkeypatch):
    llm_input_headings = []

    def fake_hierarchy_llm(df, *args, **kwargs):
        llm_input_headings.extend(df["heading"].tolist())
        return [{"id": 21, "level": 1}, {"id": 22, "level": 2}]

    monkeypatch.setattr(layout_parser, "hiearchy_llm", fake_hierarchy_llm)

    raw_heading_a = "# **1 Overview**"
    raw_heading_b = "## 2.1 Details ##"
    raw_preds = pd.DataFrame(
        [
            {"id": 21, "heading": raw_heading_a, "level": 1, "reason": "1# AND POS [1] NEG [0] META [0, 0, 1]"},
            {"id": 22, "heading": raw_heading_b, "level": 2, "reason": "2# AND POS [1] NEG [0] META [0, 0, 0]"},
        ]
    )

    result = layout_parser.est_hierarchies_llm(raw_preds, prompt_limt=1000)

    assert llm_input_headings == ["1 Overview", "2.1 Details"]
    assert result["heading"].tolist() == [raw_heading_a, raw_heading_b]
    assert result["level"].tolist() == [1, 2]
