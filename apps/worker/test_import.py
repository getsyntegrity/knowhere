#!/usr/bin/env python3
"""测试Worker服务导入"""
import sys
from pathlib import Path

# 从worker.py的位置计算monorepo根目录
worker_file = Path(__file__).resolve()
project_root = worker_file.parent
monorepo_root = project_root.parent.parent
shared_python_path = monorepo_root / "packages" / "shared-python"

# 设置 PYTHONPATH
sys.path.insert(0, str(shared_python_path))
sys.path.insert(0, str(project_root))

print(f"Worker file: {worker_file}")
print(f"Monorepo root: {monorepo_root}")
print(f"Shared path: {shared_python_path}")
print(f"Shared exists: {shared_python_path.exists()}")
print(f"\nPython path (first 3):")
for i, p in enumerate(sys.path[:3]):
    print(f"  {i}: {p}")

try:
    from app.core.celery_app import celery_app
    print("\n✅ 成功导入celery_app")
    print(f"Celery app name: {celery_app.main}")
except Exception as e:
    print(f"\n❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

