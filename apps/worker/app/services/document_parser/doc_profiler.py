"""
Agentic Document Profiler

Before data enters the pipeline, use lightweight analysis (~50ms) to generate DocProfile,
driving routing decisions and type annotations.

Usage:
    from app.services.document_parser.doc_profiler import profile_document
    profile = profile_document("/path/to/file.pdf")
"""

import os
from dataclasses import dataclass, field, asdict
from typing import Optional, Literal, List
import json

from loguru import logger

from app.services.document_parser.pymupdf_subprocess import run_in_child_process, worker


@dataclass
class DocProfile:
    """Profile data structure"""
    # ── Basic information ──
    file_type: str = ""                     # "pdf", "docx", "pptx", ...
    
    # ── Routing decision ──
    route: Literal["fast", "standard"] = "standard"
    
    # ── Document type ──
    scan_type: Optional[Literal["electronic", "scanned", "mixed"]] = None
    doc_category: Literal["generic", "atlas", "ppt_converted"] = "generic"
    
    # ── Raw features ──
    page_count: int = 0
    avg_text_density: float = 0.0         # average text density per page
    avg_image_coverage: float = 0.0       # average image coverage per page (0-1)
    has_tables: bool = False
    has_embedded_fonts: bool = False
    is_multi_column: bool = False      # multi-column layout detected
    sample_text: str = ""                 # first 500 characters
    
    # ── Page details for debug ──
    page_details: List[dict] = field(default_factory=list)
    
    # ── Reasoning ──
    reasoning: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dict (excluding page_details to reduce size)"""
        d = asdict(self)
        d.pop("page_details", None)
        d.pop("sample_text", None)
        return d
    
    def summary(self) -> str:
        """One-line summary"""
        return (
            f"[{self.file_type.upper()}] route={self.route}, "
            f"scan={self.scan_type}, category={self.doc_category}, "
            f"pages={self.page_count}, text_density={self.avg_text_density:.0f}, "
            f"img_coverage={self.avg_image_coverage:.1%}"
        )


# ─── PDF Profiling ──────────────────────────────────────

# Thresholds
SCAN_TEXT_THRESHOLD = 50         # chars per page < this → scanned page
SCAN_IMAGE_COVERAGE_MIN = 0.6   # image area ratio > this → scanned page
SCAN_PAGE_RATIO = 0.7           # more than this ratio of pages are scanned → overall scanned

ATLAS_TEXT_THRESHOLD = 200       # atlas: low text per page
ATLAS_IMAGE_COVERAGE_MIN = 0.4  # atlas: high image coverage

FAST_TEXT_THRESHOLD = 100        # fast: minimum text density to confirm extractable content

MULTI_COL_GAP_RATIO = 0.15      # min gap between columns as ratio of page width
MULTI_COL_MIN_BLOCKS = 4        # min text blocks per page to evaluate columns


@worker
def _profile_pdf_worker(queue, file_path: str) -> None:
    """Child process: analyze PDF features, return profile as dict."""
    from dataclasses import asdict as _asdict
    import pymupdf

    profile = DocProfile(file_type="pdf")
    reasons = []

    try:
        doc = pymupdf.open(file_path)
    except Exception as e:
        profile.reasoning = f"Cannot open file: {e}"
        queue.put({"ok": True, "profile": _asdict(profile)})
        return

    profile.page_count = doc.page_count

    if doc.page_count == 0:
        profile.reasoning = "Empty file (0 pages)"
        doc.close()
        queue.put({"ok": True, "profile": _asdict(profile)})
        return

    # ── Page sampling ──
    # Analyze all pages (most PDFs < 100 pages, PyMuPDF is fast)
    # For 50+ pages, use uniform sampling
    if doc.page_count <= 50:
        sample_indices = list(range(doc.page_count))
    else:
        # Uniform sample of 20 pages + first 3 + last 3
        step = doc.page_count // 20
        sample_indices = list(range(0, doc.page_count, step))[:20]
        sample_indices = sorted(set(sample_indices + [0, 1, 2] +
                                     [doc.page_count-3, doc.page_count-2, doc.page_count-1]))
        sample_indices = [i for i in sample_indices if 0 <= i < doc.page_count]

    page_details = []
    total_text_len = 0
    total_image_coverage = 0.0
    scanned_pages = 0
    all_text_parts = []
    has_any_fonts = False
    has_any_tables = False
    multi_col_pages = 0
    landscape_pages = 0
    doc_page_sizes = []

    for idx in sample_indices:
        page = doc[idx]
        page_width = page.rect.width
        page_height = page.rect.height
        page_area = page_width * page_height

        if page_width > page_height:
            landscape_pages += 1
        doc_page_sizes.append((page_width, page_height))

        text = page.get_text().strip()
        text_len = len(text)
        total_text_len += text_len

        if len("".join(all_text_parts)) < 500:
            all_text_parts.append(text[:200])

        images = page.get_images(full=True)
        img_total_area = 0.0
        for img in images:
            xref = img[0]
            try:
                rects = page.get_image_rects(xref)
                for rect in rects:
                    img_total_area += rect.width * rect.height
            except Exception:
                pass

        img_coverage = img_total_area / page_area if page_area > 0 else 0
        img_coverage = min(img_coverage, 1.0)
        total_image_coverage += img_coverage

        fonts = page.get_fonts()
        if fonts:
            has_any_fonts = True

        drawings = page.get_drawings()
        line_count = 0
        for d in drawings:
            for item in d.get("items", []):
                if item[0] in ("l", "re"):
                    line_count += 1
        if line_count >= 10:
            has_any_tables = True

        blocks = page.get_text("blocks")
        text_blocks = [b for b in blocks if b[6] == 0 and (b[2] - b[0]) > 20 and (b[3] - b[1]) > 10]

        is_multi_col_page = False
        if len(text_blocks) >= MULTI_COL_MIN_BLOCKS:
            pw = page.rect.width
            min_x_gap = pw * MULTI_COL_GAP_RATIO
            side_by_side_count = 0

            for i in range(len(text_blocks)):
                for j in range(i + 1, len(text_blocks)):
                    bi, bj = text_blocks[i], text_blocks[j]
                    y_overlap = min(bi[3], bj[3]) - max(bi[1], bj[1])
                    if y_overlap <= 0:
                        continue
                    x_gap = max(bj[0] - bi[2], bi[0] - bj[2])
                    if x_gap > min_x_gap:
                        side_by_side_count += 1
                        if side_by_side_count >= 3:
                            is_multi_col_page = True
                            break
                if is_multi_col_page:
                    break

        if is_multi_col_page:
            multi_col_pages += 1

        is_scan_page = (text_len < SCAN_TEXT_THRESHOLD and
                        img_coverage > SCAN_IMAGE_COVERAGE_MIN)
        if is_scan_page:
            scanned_pages += 1

        page_details.append({
            "page": idx + 1,
            "text_len": text_len,
            "image_count": len(images),
            "img_coverage": round(img_coverage, 3),
            "font_count": len(fonts),
            "is_scan_page": is_scan_page,
        })

    doc.close()

    # ── Aggregate features ──
    n_sampled = len(sample_indices)
    profile.avg_text_density = total_text_len / n_sampled if n_sampled > 0 else 0
    profile.avg_image_coverage = total_image_coverage / n_sampled if n_sampled > 0 else 0
    profile.has_embedded_fonts = has_any_fonts
    profile.has_tables = has_any_tables
    profile.is_multi_column = multi_col_pages > (n_sampled * 0.3)
    profile.sample_text = " ".join(all_text_parts)[:500]
    profile.page_details = page_details

    # ── Determine scan_type ──
    scan_ratio = scanned_pages / n_sampled if n_sampled > 0 else 0

    if scan_ratio >= SCAN_PAGE_RATIO:
        profile.scan_type = "scanned"
        reasons.append(f"scanned: {scanned_pages}/{n_sampled} pages are scanned ({scan_ratio:.0%})")
    elif scanned_pages > 0:
        profile.scan_type = "mixed"
        reasons.append(f"mixed: {scanned_pages}/{n_sampled} pages are scanned")
    else:
        profile.scan_type = "electronic"
        reasons.append(f"electronic: all sampled pages contain text (avg={profile.avg_text_density:.0f} chars/page)")

    # ── Determine doc_category ──
    is_atlas = (
        profile.avg_text_density < ATLAS_TEXT_THRESHOLD and
        profile.avg_image_coverage > ATLAS_IMAGE_COVERAGE_MIN
    )

    if is_atlas:
        profile.doc_category = "atlas"
        reasons.append(
            f"atlas: pages={profile.page_count}, "
            f"text={profile.avg_text_density:.0f}<{ATLAS_TEXT_THRESHOLD}, "
            f"img={profile.avg_image_coverage:.1%}>{ATLAS_IMAGE_COVERAGE_MIN:.0%}"
        )
    else:
        profile.doc_category = "generic"

    # PPT-converted detection
    landscape_ratio = landscape_pages / n_sampled if n_sampled > 0 else 0
    if landscape_ratio >= 0.8 and profile.doc_category == "generic":
        slide_ratios = [1.333, 1.778, 1.600]
        tolerance = 0.05
        ref_page = doc_page_sizes[0] if doc_page_sizes else None
        if ref_page:
            page_ratio = ref_page[0] / ref_page[1] if ref_page[1] > 0 else 0
            is_slide_ratio = any(abs(page_ratio - sr) < tolerance for sr in slide_ratios)
            if is_slide_ratio:
                profile.doc_category = "ppt_converted"
                reasons.append(
                    f"ppt_converted: {landscape_pages}/{n_sampled} landscape ({landscape_ratio:.0%}), "
                    f"ratio={page_ratio:.2f} matches slide format"
                )

    # ── Determine route ──
    if profile.scan_type == "scanned" or profile.doc_category in ("atlas", "ppt_converted"):
        profile.route = "standard"
        reasons.append(f"route=standard: requires VLM visual understanding")
    elif profile.is_multi_column:
        profile.route = "standard"
        reasons.append(f"route=standard: multi-column layout")
    elif profile.avg_text_density >= FAST_TEXT_THRESHOLD:
        profile.route = "fast"
        reasons.append(
            f"route=fast: single-column electronic PDF "
            f"(text={profile.avg_text_density:.0f}>={FAST_TEXT_THRESHOLD}, "
            f"tables={profile.has_tables}, multi_col={profile.is_multi_column})"
        )
    else:
        profile.route = "standard"
        reasons.append(f"route=standard: low text density ({profile.avg_text_density:.0f}<{FAST_TEXT_THRESHOLD})")

    profile.reasoning = " | ".join(reasons)
    queue.put({"ok": True, "profile": _asdict(profile)})


def _profile_pdf(file_path: str) -> DocProfile:
    """Profile a PDF by running PyMuPDF analysis in a spawned child process."""
    result = run_in_child_process(_profile_pdf_worker, file_path, timeout=60)
    return DocProfile(**result["profile"])


# ─── General Entry Point ────────────────────────────────

def profile_document(file_path: str, filename: str = "") -> DocProfile:
    """
    General document profiling entry point.
    
    Args:
        file_path: Local file path
        filename: File name (used to infer type)
    
    Returns:
        DocProfile
    """
    if not filename:
        filename = os.path.basename(file_path)
    
    ext = os.path.splitext(filename)[1].lower()
    
    if ext == ".pdf":
        return _profile_pdf(file_path)
    # Future extensions:
    # elif ext == ".docx":
    #     return _profile_docx(file_path)
    # elif ext == ".pptx":
    #     return _profile_pptx(file_path)
    else:
        # Non-PDF formats: return default profile for now
        return DocProfile(file_type=ext.lstrip("."), route="standard",
                          reasoning=f"Non-PDF format ({ext}), using default route")


def save_profile_metadata(profile: DocProfile, output_dir: str):
    """Save profile to output_dir/profile.json"""
    profile_path = os.path.join(output_dir, "profile.json")
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
    logger.debug(f"Profile metadata saved to {profile_path}")
