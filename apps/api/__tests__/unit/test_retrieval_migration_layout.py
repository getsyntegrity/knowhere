from pathlib import Path


def test_retrieval_schema_uses_single_alembic_revision() -> None:
    versions_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    retrieval_revisions = sorted(
        path.name
        for path in versions_dir.glob("*.py")
        if "retrieval" in path.name or "graph_routing" in path.name or "hit_stats" in path.name
    )

    assert retrieval_revisions == [
        "c3d4e5f6a7b8_add_retrieval_service_v1.py",
    ]
