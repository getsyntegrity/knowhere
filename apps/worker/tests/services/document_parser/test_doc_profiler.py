import types

from app.services.document_parser import doc_profiler


class FakeRect:
    width = 100.0
    height = 200.0


class FakePage:
    def __init__(self) -> None:
        self.rect = FakeRect()

    def get_text(self, mode=None):
        if mode == "blocks":
            return [(0.0, 0.0, 80.0, 30.0, "hello world", 0, 0)]
        return "hello world"

    def get_images(self, full=True):
        return []

    def get_fonts(self):
        return []

    def get_drawings(self):
        return []


class FakeDocument:
    def __init__(self) -> None:
        self.page_count = 1
        self.closed = False
        self.page = FakePage()

    def __getitem__(self, index: int) -> FakePage:
        assert index == 0
        return self.page

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


def test_profile_pdf_worker_closes_document_and_collects_before_queue_put(monkeypatch):
    fake_doc = FakeDocument()
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
    assert fake_queue.items[0]["profile"]["page_count"] == 1
