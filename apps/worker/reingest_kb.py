"""
reingest_kb.py — 清库并从 ~/.knowhere/chengke_kb 重新入库

操作顺序：
  1. 清除 DB 中所有 debug_local_user / local-dev-user 的文档数据
  2. 遍历 KB 目录，对每个有 chunks.json + doc_nav.json 的子目录调用 _run_db_publication()
  3. 验证入库结果（nav_sections 非空）
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../packages/shared-python'))
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
os.environ['LOCAL_DEBUG'] = '1'

from loguru import logger  # noqa: E402

KB_BASE = os.path.expanduser('~/.knowhere/chengke_kb')
CLEAN_USER_IDS = ['debug_local_user', 'local-dev-user']


# ── Step 1: 清库 ──────────────────────────────────────────
def clean_db():
    from shared.core.database_sync import get_sync_db_context
    from sqlalchemy import text

    logger.info('━' * 60)
    logger.info('  Step 1: 清除 DB 中旧数据')
    logger.info('━' * 60)

    with get_sync_db_context() as db:
        for uid in CLEAN_USER_IDS:
            # 查出该 user 下所有 document_id
            doc_ids = [r[0] for r in db.execute(
                text("SELECT document_id FROM documents WHERE user_id=:u"), {'u': uid}
            ).all()]

            if not doc_ids:
                logger.info(f'  user={uid}: 无文档，跳过')
                continue

            logger.info(f'  user={uid}: 删除 {len(doc_ids)} 个文档')

            for did in doc_ids:
                db.execute(text('DELETE FROM graph_nodes WHERE owner_document_id=:d'), {'d': did})
                db.execute(text('DELETE FROM document_chunks WHERE document_id=:d'), {'d': did})
                db.execute(text('DELETE FROM document_sections WHERE document_id=:d'), {'d': did})
                db.execute(text('DELETE FROM documents WHERE document_id=:d'), {'d': did})

            # 清 job_results / jobs
            db.execute(text(
                "DELETE FROM job_results WHERE job_id IN "
                "(SELECT job_id FROM jobs WHERE user_id=:u)"
            ), {'u': uid})
            db.execute(text('DELETE FROM jobs WHERE user_id=:u'), {'u': uid})
            db.flush()
            logger.info(f'  ✅ user={uid} 数据已清除')

        db.commit()
        logger.info('  ✅ 清库完成')


# ── Step 2: 重新入库 ──────────────────────────────────────
def ingest_all():
    # 直接复用 debug_parse.py 的 _run_db_publication
    from debug_parse import _run_db_publication

    logger.info('\n' + '━' * 60)
    logger.info('  Step 2: 重新入库')
    logger.info(f'  KB_BASE: {KB_BASE}')
    logger.info('━' * 60)

    dirs = sorted([
        d for d in os.listdir(KB_BASE)
        if os.path.isdir(os.path.join(KB_BASE, d)) and not d.startswith('.')
    ])

    success, failed = 0, 0
    for dname in dirs:
        add_dir = os.path.join(KB_BASE, dname)
        chunks_path = os.path.join(add_dir, 'chunks.json')
        nav_path = os.path.join(add_dir, 'doc_nav.json')

        if not os.path.exists(chunks_path) or not os.path.exists(nav_path):
            logger.warning(f'  ⚠️  跳过 {dname}（缺 chunks.json 或 doc_nav.json）')
            continue

        # 加载 chunks
        with open(chunks_path, encoding='utf-8') as f:
            raw = json.load(f)
        chunks = raw if isinstance(raw, list) else raw.get('chunks', [])

        source_file_name = dname  # 目录名即为源文件名
        logger.info(f'\n  ▸ {source_file_name}  ({len(chunks)} chunks)')

        try:
            _run_db_publication(
                chunks=chunks,
                add_dir=add_dir,
                source_file_name=source_file_name,
            )
            success += 1
        except Exception as e:
            logger.exception(f'  ❌ 入库失败: {dname}: {e}')
            failed += 1

    logger.info(f'\n  入库结束: ✅ {success} 成功  ❌ {failed} 失败')


# ── Step 3: 验证 ──────────────────────────────────────────
def verify():
    from shared.core.database_sync import get_sync_db_context
    from sqlalchemy import text

    logger.info('\n' + '━' * 60)
    logger.info('  Step 3: 验证入库结果')
    logger.info('━' * 60)

    with get_sync_db_context() as db:
        rows = db.execute(text(
            "SELECT d.document_id, d.source_file_name, d.user_id, "
            "  (SELECT count(*) FROM document_chunks dc WHERE dc.document_id=d.document_id) as chunks, "
            "  (SELECT count(*) FROM document_sections ds WHERE ds.document_id=d.document_id) as sections "
            "FROM documents d WHERE d.user_id='debug_local_user' ORDER BY d.created_at"
        )).all()

        logger.info(f'  共 {len(rows)} 个文档:')
        all_ok = True
        for doc_id, fname, uid, chunks, sections in rows:
            ns = db.execute(text(
                "SELECT properties->'nav_sections' FROM graph_nodes "
                "WHERE owner_document_id=:d AND node_kind='document'"
            ), {'d': doc_id}).scalar()
            ns_count = len(ns) if isinstance(ns, list) else 0

            ok = chunks > 0 and ns_count > 0
            icon = '✅' if ok else '❌'
            logger.info(f'  {icon} [{doc_id[:8]}] {str(fname)[:50]:50s}  '
                        f'chunks={chunks}  sections={sections}  nav_sections={ns_count}')
            if not ok:
                all_ok = False

        if all_ok and rows:
            logger.info('\n  ✅ 所有文档 nav_sections 非空，入库成功')
        elif not rows:
            logger.error('\n  ❌ 没有找到任何文档，入库可能失败')
        else:
            logger.warning('\n  ⚠️  部分文档 nav_sections 为空，请检查 doc_nav.json')


if __name__ == '__main__':
    clean_db()
    ingest_all()
    verify()
