#!/usr/bin/env python3
"""测试Worker服务导入"""
import sys

print("测试导入共享包...")

try:
    from shared.core.celery_app import celery_app
    print("\n✅ 成功导入celery_app")
    print(f"Celery app name: {celery_app.main}")
except Exception as e:
    print(f"\n❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ 所有导入测试通过！")
