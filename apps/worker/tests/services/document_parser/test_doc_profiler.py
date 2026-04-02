import types

from app.services.document_parser import doc_profiler


class FakeRect:
    def __init__(self, width: float = 100.0, height: float = 200.0) -> None:
        self.width = width
        self.height = height


class FakeTableFinder:
    def __init__(self, table_count: int = 0) -> None:
        self.tables = [object() for _ in range(table_count)]


class FakePage:
    def __init__(
        self,
        *,
        text: str = "hello world",
        rect: FakeRect | None = None,
        images: list[tuple] | None = None,
        image_rects: dict[int, list[FakeRect]] | None = None,
        fonts: list | None = None,
        drawings: list[dict] | None = None,
        blocks: list[tuple] | None = None,
        table_count: int = 0,
    ) -> None:
        self.rect = rect or FakeRect()
        self._text = text
        self._images = images or []
        self._image_rects = image_rects or {}
        self._fonts = fonts or []
        self._drawings = drawings or []
        self._blocks = blocks or [(0.0, 0.0, 80.0, 30.0, text, 0, 0)]
        self._table_count = table_count

    def get_text(self, mode=None):
        if mode == "blocks":
            return self._blocks
        return self._text

    def get_images(self, full=True):
        return self._images

    def get_image_rects(self, xref: int):
        return self._image_rects.get(xref, [])

    def get_fonts(self):
        return self._fonts

    def get_drawings(self):
        return self._drawings

    def find_tables(self):
        return FakeTableFinder(self._table_count)


def _filled_rect_drawing() -> dict:
    return {
        "items": [("re", FakeRect(width=80.0, height=30.0))],
        "fill": (1.0, 1.0, 1.0),
        "color": None,
        "width": None,
    }


def _filled_line_box_drawing() -> dict:
    return {
        "items": [
            ("l", types.SimpleNamespace(x=0.0, y=0.0), types.SimpleNamespace(x=80.0, y=0.0)),
            ("l", types.SimpleNamespace(x=80.0, y=0.0), types.SimpleNamespace(x=80.0, y=30.0)),
            ("l", types.SimpleNamespace(x=80.0, y=30.0), types.SimpleNamespace(x=0.0, y=30.0)),
            ("l", types.SimpleNamespace(x=0.0, y=30.0), types.SimpleNamespace(x=0.0, y=0.0)),
        ],
        "fill": (1.0, 1.0, 1.0),
        "color": None,
        "width": None,
    }


def _stroked_table_box_drawing() -> dict:
    return {
        "items": [
            ("l", types.SimpleNamespace(x=0.0, y=0.0), types.SimpleNamespace(x=80.0, y=0.0)),
            ("l", types.SimpleNamespace(x=80.0, y=0.0), types.SimpleNamespace(x=80.0, y=30.0)),
            ("l", types.SimpleNamespace(x=80.0, y=30.0), types.SimpleNamespace(x=0.0, y=30.0)),
            ("l", types.SimpleNamespace(x=0.0, y=30.0), types.SimpleNamespace(x=0.0, y=0.0)),
            ("l", types.SimpleNamespace(x=20.0, y=0.0), types.SimpleNamespace(x=20.0, y=30.0)),
            ("l", types.SimpleNamespace(x=40.0, y=0.0), types.SimpleNamespace(x=40.0, y=30.0)),
            ("l", types.SimpleNamespace(x=60.0, y=0.0), types.SimpleNamespace(x=60.0, y=30.0)),
            ("l", types.SimpleNamespace(x=0.0, y=10.0), types.SimpleNamespace(x=80.0, y=10.0)),
            ("l", types.SimpleNamespace(x=0.0, y=20.0), types.SimpleNamespace(x=80.0, y=20.0)),
            ("l", types.SimpleNamespace(x=0.0, y=15.0), types.SimpleNamespace(x=80.0, y=15.0)),
            ("l", types.SimpleNamespace(x=30.0, y=0.0), types.SimpleNamespace(x=30.0, y=30.0)),
            ("l", types.SimpleNamespace(x=50.0, y=0.0), types.SimpleNamespace(x=50.0, y=30.0)),
        ],
        "fill": None,
        "color": (0.0, 0.0, 0.0),
        "width": 1.0,
    }


class FakeDocument:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages
        self.page_count = len(pages)
        self.closed = False

    def __getitem__(self, index: int) -> FakePage:
        return self.pages[index]

    def close(self) -> None:
        self.closed = True


class FakeQueue:
    def __init__(self, doc: FakeDocument, collect_calls: list[str]) -> None:
        self.doc = doc
        self.collect_calls = collect_calls
        self.items = []
        self.doc_closed_at_put = False
        self.gc_collect_count_at_put = 0

    def put(self, payload: dict) -> None:
        self.doc_closed_at_put = self.doc.closed
        self.gc_collect_count_at_put = len(self.collect_calls)
        self.items.append(payload)


def _run_profile_worker(monkeypatch, pages: list[FakePage]) -> dict:
    fake_doc = FakeDocument(pages)
    fake_queue = FakeQueue(fake_doc, collect_calls=[])
    collect_calls = fake_queue.collect_calls

    fake_pymupdf = types.SimpleNamespace(open=lambda path: fake_doc)

    monkeypatch.setitem(__import__("sys").modules, "pymupdf", fake_pymupdf)
    monkeypatch.setattr(doc_profiler.gc, "collect", lambda: collect_calls.append("gc"))

    doc_profiler._profile_pdf_worker(fake_queue, "/tmp/sample.pdf")

    assert fake_doc.closed is True
    assert fake_queue.doc_closed_at_put is True
    assert fake_queue.gc_collect_count_at_put == 1
    assert fake_queue.items[0]["ok"] is True
    return fake_queue.items[0]["profile"]


def test_profile_pdf_worker_closes_document_and_collects_before_queue_put(monkeypatch):
    profile = _run_profile_worker(monkeypatch, [FakePage()])
    assert profile["page_count"] == 1


def test_profile_pdf_worker_marks_safe_fast_for_dense_text_pdf(monkeypatch):
    dense_text = "A" * 1400
    pages = [FakePage(text=dense_text) for _ in range(12)]

    profile = _run_profile_worker(monkeypatch, pages)

    assert profile["scan_type"] == "electronic"
    assert profile["route"] == "fast"
    assert profile["decision_band"] == "safe_fast"
    assert profile["has_detected_tables"] is False
    assert profile["has_significant_images"] is False


def test_profile_pdf_worker_marks_safe_standard_for_detected_tables(monkeypatch):
    dense_text = "A" * 1400
    pages = [FakePage(text=dense_text) for _ in range(11)]
    pages.append(FakePage(text=dense_text, drawings=[_stroked_table_box_drawing()]))

    profile = _run_profile_worker(monkeypatch, pages)

    assert profile["has_detected_tables"] is True
    assert profile["route"] == "standard"
    assert profile["decision_band"] == "safe_standard"


def test_profile_pdf_worker_ignores_find_tables_only_hits(monkeypatch):
    dense_text = "A" * 1400
    pages = [FakePage(text=dense_text) for _ in range(11)]
    pages.append(FakePage(text=dense_text, table_count=1))

    profile = _run_profile_worker(monkeypatch, pages)

    assert profile["has_detected_tables"] is False
    assert profile["route"] == "fast"
    assert profile["decision_band"] == "safe_fast"


def test_profile_pdf_worker_marks_gray_zone_for_borderline_image_mix(monkeypatch):
    dense_text = "A" * 1400
    pages = [FakePage(text=dense_text) for _ in range(11)]
    pages.append(
        FakePage(
            text=dense_text,
            images=[
                (1, 0, 200, 120),
                (2, 0, 200, 120),
                (3, 0, 200, 120),
                (4, 0, 200, 120),
                (5, 0, 200, 120),
                (6, 0, 200, 120),
            ],
            image_rects={
                1: [FakeRect(width=30, height=20)],
                2: [FakeRect(width=30, height=20)],
                3: [FakeRect(width=30, height=20)],
                4: [FakeRect(width=30, height=20)],
                5: [FakeRect(width=30, height=20)],
                6: [FakeRect(width=30, height=20)],
            },
        )
    )

    profile = _run_profile_worker(monkeypatch, pages)

    assert profile["has_significant_images"] is True
    assert profile["route"] == "standard"
    assert profile["decision_band"] == "gray_zone"


def test_profile_pdf_worker_ignores_fill_only_rectangles_for_text_pdf(monkeypatch):
    dense_text = "A" * 900
    filled_rect_drawings = [_filled_rect_drawing() for _ in range(20)]
    pages = [FakePage(text=dense_text, drawings=filled_rect_drawings) for _ in range(12)]

    profile = _run_profile_worker(monkeypatch, pages)

    assert profile["has_detected_tables"] is False
    assert profile["complex_page_ratio"] == 0.0
    assert profile["route"] == "fast"
    assert profile["decision_band"] == "safe_fast"


def test_profile_pdf_worker_marks_short_clean_text_pdf_as_safe_fast(monkeypatch):
    pages = [FakePage(text="A" * 438) for _ in range(3)]

    profile = _run_profile_worker(monkeypatch, pages)

    assert profile["has_detected_tables"] is False
    assert profile["complex_page_ratio"] == 0.0
    assert profile["route"] == "fast"
    assert profile["decision_band"] == "safe_fast"


def test_profile_pdf_worker_keeps_near_empty_pdf_out_of_safe_fast(monkeypatch):
    pages = [FakePage(text="A" * 20) for _ in range(3)]

    profile = _run_profile_worker(monkeypatch, pages)

    assert profile["route"] == "standard"
    assert profile["decision_band"] == "gray_zone"


def test_profile_pdf_worker_ignores_fill_only_line_boxes_for_text_pdf(monkeypatch):
    dense_text = "A" * 700
    drawings = [_filled_line_box_drawing() for _ in range(10)]
    pages = [FakePage(text=dense_text, drawings=drawings) for _ in range(8)]

    profile = _run_profile_worker(monkeypatch, pages)

    assert profile["has_detected_tables"] is False
    assert profile["complex_page_ratio"] == 0.0
    assert profile["route"] == "fast"
    assert profile["decision_band"] == "safe_fast"
