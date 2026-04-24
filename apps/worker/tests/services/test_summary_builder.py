from app.services.connect_builder.summary_builder import _build_chunk_lookup, _extract_top_summary


def test_extract_top_summary_uses_root_summary_only_for_llm_mode() -> None:
    hierarchy = {
        "Root": {
            "demo.pdf": {
                "_summary": "This manual explains TIG parameter selection for stainless steel welds.",
                "Introduction": {"_summary": "Section intro."},
                "Setup": {"_summary": "Section setup."},
            }
        }
    }

    result = _extract_top_summary(hierarchy, "demo.pdf")

    assert result == "This manual explains TIG parameter selection for stainless steel welds."
    assert "This document includes the following contents:" not in result


def test_extract_top_summary_supplements_title_enum_summary() -> None:
    hierarchy = {
        "Root": {
            "demo.pdf": {
                "_summary": "This section covers: Introduction, Setup, Operation, Appendix.",
                "Introduction": {"_summary": "Overview of the equipment."},
                "Setup": {"_summary": "Installation steps."},
                "Operation": {"_summary": "Operating workflow."},
                "Appendix": {"_summary": "Reference tables."},
            }
        }
    }

    result = _extract_top_summary(hierarchy, "demo.pdf")

    assert result.startswith("This section covers: Introduction, Setup, Operation, Appendix.")
    assert "This document includes the following contents:" in result
    assert "- Introduction" in result
    assert "- Appendix" in result


def test_extract_top_summary_uses_bfs_titles_for_non_llm_documents() -> None:
    hierarchy = {
        "Root": {
            "demo.pdf": {
                "_summary": "This section covers: Main Body.",
                "Main Body": {
                    "_summary": "This section covers: Safety, Setup.",
                    "Safety": {"_summary": "This section covers: PPE."},
                    "Setup": {"_summary": "This section covers: Wiring."},
                    "Operation": {"_summary": "This section covers: Procedure."},
                    "Appendix": {"_summary": "This section covers: Tables."},
                },
            }
        }
    }

    result = _extract_top_summary(hierarchy, "demo.pdf")

    assert "This document includes the following contents:" in result
    assert "- Main Body" in result
    assert "  - Safety" in result
    assert "  - Appendix" in result


def test_extract_top_summary_limits_tree_to_two_levels() -> None:
    hierarchy = {
        "Root": {
            "demo.pdf": {
                "_summary": "This section covers: Chapter 1.",
                "Chapter 1": {
                    "_summary": "This section covers: Safety.",
                    "Safety": {
                        "_summary": "This section covers: PPE.",
                        "PPE": {"_summary": "This section covers: Gloves."},
                    },
                },
            }
        }
    }

    result = _extract_top_summary(hierarchy, "demo.pdf")

    assert "- Chapter 1" in result
    assert "  - Safety" in result
    assert "    - PPE" not in result


def test_extract_top_summary_keeps_overlong_first_sentence() -> None:
    long_sentence = "A" * 230 + ". Second sentence should never be included."
    hierarchy = {
        "Root": {
            "demo.pdf": {
                "_summary": long_sentence,
                "Section A": {"_summary": "Ignored."},
            }
        }
    }

    result = _extract_top_summary(hierarchy, "demo.pdf")

    assert result == ("A" * 230 + ".")
    assert len(result) > 200


def test_build_chunk_lookup_uses_title_and_keywords_only_when_summary_missing() -> None:
    lookup = _build_chunk_lookup([
        {
            "path": "demo.pdf/Section A",
            "type": "text",
            "content": "123 = mc^2 and raw body text should be ignored",
            "metadata": {"keywords": ["tig", "argon"]},
        }
    ])

    assert lookup["Section A"] == "Section A\nKeywords: tig, argon"
