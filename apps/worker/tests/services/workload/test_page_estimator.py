"""
Tests for PageEstimator service.

Integration tests using REAL files to verify the full pipeline
including external libraries (pypdf, python-pptx, python-docx, pandas).

NO MOCKING - these are true integration tests.
"""
import math
from pathlib import Path

import pytest

from app.services.workload.page_estimator import (
    ROWS_PER_PAGE,
    WORDS_PER_PAGE,
    PageEstimator,
    count_cn_en,
)


# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"


class TestCountCnEn:
    """Tests for the count_cn_en utility function."""

    def test_empty_string(self):
        """Empty string should return 0."""
        assert count_cn_en("") == 0

    def test_none_input(self):
        """None input should return 0."""
        assert count_cn_en(None) == 0

    def test_chinese_only(self):
        """Chinese characters should be counted individually."""
        assert count_cn_en("你好世界") == 4

    def test_english_only(self):
        """English words should be counted as whole words."""
        assert count_cn_en("Hello World Test") == 3

    def test_numbers_only(self):
        """Numbers should be counted as individual tokens."""
        assert count_cn_en("123 456 789") == 3

    def test_decimal_numbers(self):
        """Decimal numbers should be counted as single tokens."""
        assert count_cn_en("3.14 2.718") == 2

    def test_mixed_content(self):
        """Mixed Chinese, English, and numbers."""
        # 你好 (2 Chinese) + Hello World (2 English) + 123 (1 number) = 5
        assert count_cn_en("你好Hello World 123") == 5

    def test_special_characters_ignored(self):
        """Special characters should not be counted."""
        assert count_cn_en("!@#$%^&*()") == 0

    def test_punctuation_not_counted(self):
        """Punctuation marks should not be counted."""
        # Only the actual word 'test' should be counted
        assert count_cn_en("test, test! test?") == 3


class TestPageEstimatorConstants:
    """Tests for billing constants."""

    def test_words_per_page_constant(self):
        """Verify WORDS_PER_PAGE constant."""
        assert WORDS_PER_PAGE == 500

    def test_rows_per_page_constant(self):
        """Verify ROWS_PER_PAGE constant."""
        assert ROWS_PER_PAGE == 50


class TestPageEstimatorPDF:
    """Integration tests for PDF file estimation using real PDF files."""

    def test_pdf_3_pages(self):
        """PDF with 3 pages should return 3."""
        pdf_path = FIXTURES_DIR / "sample_3pages.pdf"
        assert pdf_path.exists(), f"Fixture not found: {pdf_path}"
        assert PageEstimator.estimate(str(pdf_path)) == 3

    def test_nonexistent_pdf_returns_1(self):
        """Nonexistent PDF should return 1 (graceful fallback)."""
        assert PageEstimator.estimate("/nonexistent/file.pdf") == 1


class TestPageEstimatorPPTX:
    """Integration tests for PPTX file estimation using real PPTX files."""

    def test_pptx_5_slides(self):
        """PPTX with 5 slides should return 5."""
        pptx_path = FIXTURES_DIR / "sample_5slides.pptx"
        assert pptx_path.exists(), f"Fixture not found: {pptx_path}"
        assert PageEstimator.estimate(str(pptx_path)) == 5

    def test_nonexistent_pptx_returns_1(self):
        """Nonexistent PPTX should return 1 (graceful fallback)."""
        assert PageEstimator.estimate("/nonexistent/file.pptx") == 1


class TestPageEstimatorDOCX:
    """Integration tests for DOCX file estimation using real DOCX files."""

    def test_docx_1000_words(self):
        """DOCX with ~1000 words should return 2 pages (1000/500)."""
        docx_path = FIXTURES_DIR / "sample_1000words.docx"
        assert docx_path.exists(), f"Fixture not found: {docx_path}"
        result = PageEstimator.estimate(str(docx_path))
        # 1000 words / 500 words per page = 2 pages
        assert result == 2, f"Expected 2 pages for 1000 words, got {result}"

    def test_docx_chinese_600_chars(self):
        """DOCX with 600 Chinese chars should return 2 pages (600/500 = 1.2 -> ceil = 2)."""
        docx_path = FIXTURES_DIR / "sample_chinese_600chars.docx"
        assert docx_path.exists(), f"Fixture not found: {docx_path}"
        result = PageEstimator.estimate(str(docx_path))
        # 600 chars / 500 = 1.2 -> ceil = 2 pages
        assert result == 2, f"Expected 2 pages for 600 Chinese chars, got {result}"

    def test_nonexistent_docx_returns_1(self):
        """Nonexistent DOCX should return 1 (graceful fallback)."""
        assert PageEstimator.estimate("/nonexistent/file.docx") == 1


class TestPageEstimatorXLSX:
    """Integration tests for XLSX file estimation using real XLSX files."""

    def test_xlsx_100_rows(self):
        """XLSX with 100 rows should return 2 pages (100/50)."""
        xlsx_path = FIXTURES_DIR / "sample_100rows.xlsx"
        assert xlsx_path.exists(), f"Fixture not found: {xlsx_path}"
        result = PageEstimator.estimate(str(xlsx_path))
        # 100 rows / 50 rows per page = 2 pages
        assert result == 2, f"Expected 2 pages for 100 rows, got {result}"

    def test_xlsx_multisheet(self):
        """XLSX with 150 total rows across sheets should return 3 pages."""
        xlsx_path = FIXTURES_DIR / "sample_multisheet.xlsx"
        assert xlsx_path.exists(), f"Fixture not found: {xlsx_path}"
        result = PageEstimator.estimate(str(xlsx_path))
        # 75 + 75 = 150 rows / 50 = 3 pages
        assert result == 3, f"Expected 3 pages for 150 rows, got {result}"

    def test_nonexistent_xlsx_returns_1(self):
        """Nonexistent XLSX should return 1 (graceful fallback)."""
        assert PageEstimator.estimate("/nonexistent/file.xlsx") == 1


class TestPageEstimatorTextFiles:
    """Integration tests for text-based file estimation using real files."""

    def test_empty_text_file(self):
        """Empty text file should return 1 page (minimum)."""
        txt_path = FIXTURES_DIR / "empty.txt"
        assert txt_path.exists(), f"Fixture not found: {txt_path}"
        assert PageEstimator.estimate(str(txt_path)) == 1

    def test_small_text_file(self):
        """Text file with 100 words should return 1 page."""
        txt_path = FIXTURES_DIR / "small.txt"
        assert txt_path.exists(), f"Fixture not found: {txt_path}"
        result = PageEstimator.estimate(str(txt_path))
        # 100 words / 500 = 0.2 -> ceil = 1 page (minimum)
        assert result == 1, f"Expected 1 page for 100 words, got {result}"

    def test_large_text_file(self):
        """Text file with 1000 words should return 2 pages."""
        txt_path = FIXTURES_DIR / "large.txt"
        assert txt_path.exists(), f"Fixture not found: {txt_path}"
        result = PageEstimator.estimate(str(txt_path))
        # 1000 words / 500 = 2 pages
        assert result == 2, f"Expected 2 pages for 1000 words, got {result}"

    def test_chinese_text_file(self):
        """Text file with 1000 Chinese chars should return 2 pages."""
        txt_path = FIXTURES_DIR / "chinese.txt"
        assert txt_path.exists(), f"Fixture not found: {txt_path}"
        result = PageEstimator.estimate(str(txt_path))
        # 1000 chars / 500 = 2 pages
        assert result == 2, f"Expected 2 pages for 1000 Chinese chars, got {result}"

    def test_markdown_file(self):
        """Markdown file should use text-based estimation."""
        md_path = FIXTURES_DIR / "sample.md"
        assert md_path.exists(), f"Fixture not found: {md_path}"
        result = PageEstimator.estimate(str(md_path))
        # ~600 words + header = ~602 words / 500 = 1.2 -> ceil = 2 pages
        assert result == 2, f"Expected 2 pages for markdown, got {result}"

    def test_json_file(self):
        """JSON file should use text-based estimation."""
        json_path = FIXTURES_DIR / "sample.json"
        assert json_path.exists(), f"Fixture not found: {json_path}"
        result = PageEstimator.estimate(str(json_path))
        # JSON with 200 items - should be at least 1 page
        assert result >= 1


class TestPageEstimatorImages:
    """Integration tests for image file estimation."""

    def test_png_returns_1(self):
        """PNG image should return 1 page."""
        png_path = FIXTURES_DIR / "sample.png"
        assert png_path.exists(), f"Fixture not found: {png_path}"
        assert PageEstimator.estimate(str(png_path)) == 1


class TestPageEstimatorUnknownTypes:
    """Tests for unknown file types."""

    def test_unknown_extension_returns_1(self, tmp_path):
        """Unknown file extension should return 1 page."""
        unknown_file = tmp_path / "file.xyz"
        unknown_file.write_text("content")
        assert PageEstimator.estimate(str(unknown_file)) == 1

    def test_uppercase_extension(self, tmp_path):
        """Uppercase extensions should be handled correctly."""
        txt_file = tmp_path / "FILE.TXT"
        txt_file.write_text("word " * 100)
        result = PageEstimator.estimate(str(txt_file))
        assert result == 1  # 100 words = 1 page


class TestPageEstimatorEdgeCases:
    """Edge case tests."""

    def test_file_with_special_characters_in_path(self, tmp_path):
        """File path with special characters should work."""
        special_dir = tmp_path / "特殊目录 (special)"
        special_dir.mkdir()
        txt_file = special_dir / "文件.txt"
        txt_file.write_text("content")
        assert PageEstimator.estimate(str(txt_file)) == 1

    def test_minimum_page_count_is_always_1(self, tmp_path):
        """Page count should never be less than 1."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")
        assert PageEstimator.estimate(str(empty_file)) >= 1

    def test_nonexistent_file_returns_1(self):
        """Nonexistent file should return 1 (not crash)."""
        assert PageEstimator.estimate("/this/path/does/not/exist.txt") == 1

    def test_calculation_accuracy(self, tmp_path):
        """Verify page calculation math is correct."""
        # Create file with exactly 750 words
        txt_file = tmp_path / "exact.txt"
        txt_file.write_text("word " * 750)
        result = PageEstimator.estimate(str(txt_file))
        # 750 / 500 = 1.5 -> ceil = 2 pages
        assert result == 2

    def test_boundary_at_500_words(self, tmp_path):
        """Test boundary condition at exactly 500 words."""
        txt_file = tmp_path / "boundary.txt"
        txt_file.write_text("word " * 500)
        result = PageEstimator.estimate(str(txt_file))
        # 500 / 500 = 1.0 -> ceil = 1 page
        assert result == 1

    def test_boundary_at_501_words(self, tmp_path):
        """Test boundary condition at 501 words."""
        txt_file = tmp_path / "boundary501.txt"
        txt_file.write_text("word " * 501)
        result = PageEstimator.estimate(str(txt_file))
        # 501 / 500 = 1.002 -> ceil = 2 pages
        assert result == 2
