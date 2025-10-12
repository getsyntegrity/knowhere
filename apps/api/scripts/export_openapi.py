#!/usr/bin/env python3
"""
导出 FastAPI OpenAPI Schema
从 main.py 导入 FastAPI app 并导出 OpenAPI schema 到 openapi.json
"""
import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from main import app
except ImportError as e:
    print(f"❌ 无法导入 FastAPI app: {e}")
    print("请确保在 apps/api 目录下运行此脚本")
    sys.exit(1)

def export_openapi():
    """导出 OpenAPI schema 到 openapi.json"""
    try:
        openapi_schema = app.openapi()
        output_path = Path(__file__).parent.parent / "openapi.json"
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(openapi_schema, f, ensure_ascii=False, indent=2)
        
        print(f"✅ OpenAPI schema 已导出到: {output_path}")
        print(f"📊 包含 {len(openapi_schema.get('paths', {}))} 个 API 端点")
        
    except Exception as e:
        print(f"❌ 导出 OpenAPI schema 失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    export_openapi()
