import sys
import types

from app.services.document_parser import pdf_parser


class FakeDocument:
    def __init__(self) -> None:
        self.close_calls = 0

    @property
    def closed(self) -> bool:
        return self.close_calls > 0

    def close(self) -> None:
        self.close_calls += 1


class FakeQueue:
    def __init__(self, doc: FakeDocument) -> None:
        self.doc = doc
        self.items = []
        self.doc_closed_at_put = False

    def put(self, payload: dict) -> None:
        self.doc_closed_at_put = self.doc.closed
        self.items.append(payload)


def test_fast_path_worker_closes_document_before_queue_put(monkeypatch, tmp_path):
    fake_doc = FakeDocument()
    queue = FakeQueue(fake_doc)
    image_dir = tmp_path / "images"
    image_dir.mkdir()

    received = {"doc": None}

    fake_pymupdf = types.SimpleNamespace(open=lambda path: fake_doc)

    def fake_to_markdown(doc, **kwargs):
        received["doc"] = doc
        return "# mock markdown"

    fake_pymupdf4llm = types.SimpleNamespace(to_markdown=fake_to_markdown)

    monkeypatch.setitem(sys.modules, "pymupdf", fake_pymupdf)
    monkeypatch.setitem(sys.modules, "pymupdf4llm", fake_pymupdf4llm)
    monkeypatch.setattr(pdf_parser, "_inject_page_markers_pymupdf", lambda pdf_path, output_dir: None)

    pdf_parser._fast_path_worker(
        queue,
        str(tmp_path / "sample.pdf"),
        str(tmp_path),
        str(image_dir),
    )

    assert received["doc"] is fake_doc
    assert fake_doc.close_calls == 1
    assert queue.doc_closed_at_put is True
    assert queue.items == [{"ok": True, "md_chars": 15, "image_count": 0}]
