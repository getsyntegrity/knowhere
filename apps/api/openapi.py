from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
import jsonref

def custom_openapi(app: FastAPI):
    if app.openapi_schema:
        return app.openapi_schema
    
    # 1. 获取默认的 OpenAPI 字典
    openapi_schema = get_openapi(
        title="Custom API",
        version="1.0.0",
        routes=app.routes,
    )
    
    # 2. 使用 jsonref 解析所有的 $ref 并替换为原始数据
    # replace_refs=True 会将所有引用替换为实际内容
    resolved_schema = jsonref.replace_refs(openapi_schema)
    
    # 注意：jsonref 返回的是包装对象，转回普通 dict
    app.openapi_schema = dict(resolved_schema)
    return app.openapi_schema
