#!/usr/bin/env python3
"""
Rebuild knowledge_graph.json, chunk_stats.json, and chunks_slim.json
for a specified local knowledge base.

Usage:
    python rebuild_kb.py chengke_kb
"""
import json
import os
import sys

# Add project paths
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, "apps", "worker"))
sys.path.insert(0, os.path.join(project_root, "packages", "shared-python"))

from app.services.connect_builder.graph_builder import (
    build_knowledge_graph,
    save_knowledge_graph,
    _load_all_chunks_from_kb,
    load_chunk_stats,
)
from app.services.connect_builder.builder import build_connections

KNOWHERE_HOME = os.path.expanduser(os.environ.get("KNOWHERE_HOME", "~/.knowhere"))

def generate_slim(kb_dir: str):
    """Generate chunks_slim.json for all documents in a KB."""
    count = 0
    for entry in os.listdir(kb_dir):
        entry_path = os.path.join(kb_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        chunks_file = os.path.join(entry_path, "chunks.json")
        slim_file = os.path.join(entry_path, "chunks_slim.json")
        if not os.path.isfile(chunks_file):
            continue
        try:
            with open(chunks_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            chunks = data.get("chunks", data) if isinstance(data, dict) else data
            if not isinstance(chunks, list):
                continue
            slim = []
            for c in chunks:
                meta = c.get("metadata", {}) if isinstance(c.get("metadata"), dict) else {}
                slim.append({
                    "type": c.get("type", "text"),
                    "path": c.get("path", ""),
                    "content": c.get("content", ""),
                    "summary": meta.get("summary") or c.get("summary", ""),
                })
            with open(slim_file, "w", encoding="utf-8") as f:
                json.dump({"chunks": slim}, f, ensure_ascii=False, indent=2)
            full_size = os.path.getsize(chunks_file)
            slim_size = os.path.getsize(slim_file)
            pct = round((1 - slim_size / full_size) * 100) if full_size else 0
            print(f"  ✅ {entry}/chunks_slim.json: {full_size//1024}K → {slim_size//1024}K (-{pct}%)")
            count += 1
        except Exception as e:
            print(f"  ❌ {entry}: {e}")
    return count


def main():
    kb_id = sys.argv[1] if len(sys.argv) > 1 else "chengke_kb"
    kb_dir = os.path.join(KNOWHERE_HOME, kb_id)

    if not os.path.isdir(kb_dir):
        print(f"❌ KB directory not found: {kb_dir}")
        sys.exit(1)

    print(f"📂 Rebuilding KB: {kb_id}")
    print(f"   Path: {kb_dir}")
    print()

    # 1. Load all chunks
    print("[1/3] Loading all chunks...")
    all_chunks = _load_all_chunks_from_kb(kb_dir)
    print(f"  Loaded {len(all_chunks)} chunks from {len(set(c.get('_source_file','') for c in all_chunks))} files")

    # 2. Build connections
    print("\n[2/3] Building connections + knowledge graph...")
    connections = build_connections(all_chunks)
    total_conns = sum(len(v) for v in connections.values())
    print(f"  Found {total_conns} connections")

    # Build graph
    chunk_stats = load_chunk_stats(kb_id)
    graph = build_knowledge_graph(all_chunks, connections, kb_id=kb_id, chunk_stats=chunk_stats)

    # Save
    kg_path = os.path.join(kb_dir, "knowledge_graph.json")
    save_knowledge_graph(graph, kg_path)
    print(f"  Saved: {kg_path}")
    print(f"  Files: {graph['stats']['total_files']}, Chunks: {graph['stats']['total_chunks']}, Edges: {graph['stats']['total_cross_file_edges']}")

    # 3. Generate chunks_slim
    print("\n[3/3] Generating chunks_slim.json...")
    count = generate_slim(kb_dir)
    print(f"  Generated {count} slim files")

    print(f"\n✅ Done! KB '{kb_id}' rebuilt successfully.")


if __name__ == "__main__":
    main()
