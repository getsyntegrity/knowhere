# knowhere-sdk-python

Knowhere Python SDK，提供类型安全的 API 客户端。

## 安装

```bash
pip install knowhere-sdk
```

## 使用方式

### 异步使用

```python
import asyncio
from knowhere_sdk import KnowhereClient, KnowhereClientConfig

async def main():
    # 创建客户端
    client = KnowhereClient({
        "base_url": "http://localhost:5006/api",
        "api_key": "your-api-key",  # 可选
        "timeout": 30,
    })

    try:
        # GET 请求
        response = await client.get("/users/123")
        print(response.data)

        # POST 请求
        new_user = await client.post("/users", {
            "name": "John Doe",
            "email": "john@example.com",
        })
        print(new_user.data)

    except Exception as e:
        print(f"API 请求失败: {e}")

# 运行异步代码
asyncio.run(main())
```

### 同步使用

```python
from knowhere_sdk import KnowhereClient

# 创建客户端
client = KnowhereClient({
    "base_url": "http://localhost:5006/api",
    "api_key": "your-api-key",
})

try:
    # 同步 GET 请求
    response = client.sync_get("/users/123")
    print(response.data)

    # 同步 POST 请求
    new_user = client.sync_post("/users", {
        "name": "John Doe",
        "email": "john@example.com",
    })
    print(new_user.data)

except Exception as e:
    print(f"API 请求失败: {e}")
```

## API

### KnowhereClient

#### 构造函数

```python
KnowhereClient(config: Union[KnowhereClientConfig, Dict[str, Any]])
```

#### 异步方法

- `get(endpoint, params=None, headers=None) -> ApiResponse`
- `post(endpoint, data=None, params=None, headers=None) -> ApiResponse`
- `put(endpoint, data=None, params=None, headers=None) -> ApiResponse`
- `patch(endpoint, data=None, params=None, headers=None) -> ApiResponse`
- `delete(endpoint, params=None, headers=None) -> ApiResponse`

#### 同步方法

- `sync_get(endpoint, params=None, headers=None) -> ApiResponse`
- `sync_post(endpoint, data=None, params=None, headers=None) -> ApiResponse`
- `sync_put(endpoint, data=None, params=None, headers=None) -> ApiResponse`
- `sync_patch(endpoint, data=None, params=None, headers=None) -> ApiResponse`
- `sync_delete(endpoint, params=None, headers=None) -> ApiResponse`

## 类型安全

SDK 支持从 FastAPI 自动生成的 Pydantic 模型，确保 API 调用的类型安全。

## 错误处理

```python
from knowhere_sdk import ApiError

try:
    response = await client.get("/users/123")
except ApiError as e:
    print(f"API 错误: {e}")
    print(f"状态码: {e.status}")
    print(f"错误数据: {e.data}")
except Exception as e:
    print(f"其他错误: {e}")
```
