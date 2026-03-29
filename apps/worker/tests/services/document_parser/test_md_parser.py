from pathlib import Path

from app.services.document_parser import md_parser


def test_parse_md_deferred_table_summary_uses_table_result_branch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        md_parser,
        "detect_tocs_in_texts",
        lambda lines, model_name=None: (None, lines),
    )
    monkeypatch.setattr(
        md_parser,
        "eval_md_headings",
        lambda md_lines, source_type, **kwargs: md_lines,
    )
    monkeypatch.setattr(
        md_parser,
        "extract_title_keywords_summary",
        lambda text, max_keywords=3, summary_len=None: (
            "LLM Table Title",
            "kw1;kw2",
            "LLM table summary",
        ),
    )

    base_llm_paras = {
        "model_name": "deepseek-chat",
        "smart_title_parse": False,
        "summary_image": False,
        "summary_table": True,
        "summary_txt": False,
        "stopwords": [],
    }
    md_lines = [
        "# Section 1",
        "<table><tr><td>Header</td></tr><tr><td>Value</td></tr></table>",
    ]

    result_df = md_parser.parse_md(
        output_dir=str(tmp_path),
        source_type="md",
        md_lines=md_lines,
        base_llm_paras=base_llm_paras,
        relative_root="doc.md",
    )

    table_rows = result_df[result_df["path"].str.startswith("tables/")]
    assert len(table_rows) == 1

    table_row = table_rows.iloc[0]
    assert table_row["keywords"] == "kw1;kw2"
    assert table_row["summary"] == "table-1\nLLM table summary"
    assert table_row["path"].startswith("tables/")
    assert table_row["path"].endswith("LLM Table Title.html")
