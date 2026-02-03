from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
import jsonref

def custom_openapi(app: FastAPI):
    if app.openapi_schema:
        return app.openapi_schema
    
    # 1. Get default OpenAPI dictionary
    openapi_schema = get_openapi(
        title="Custom API",
        version="1.0.0",
        routes=app.routes,
    )
    
    # 2. Use jsonref to resolve all $refs and replace with raw data
    # replace_refs=True will replace all references with actual content
    # proxies=False ensures return of pure Python objects (dict/list) instead of jsonref proxy objects
    # Otherwise FastAPI's json.dumps will raise TypeError: Object of type dict is not JSON serializable
    resolved_schema = jsonref.replace_refs(openapi_schema, proxies=False)
    
    app.openapi_schema = resolved_schema
    return app.openapi_schema
