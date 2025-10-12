import httpx
from typing import Optional

http_client: Optional[httpx.AsyncClient] = None
def get_http_client() -> httpx.AsyncClient:
    if http_client is None:
        raise RuntimeError("HTTP client has not been initialized. Is it in the lifespan manager?")
    return http_client
