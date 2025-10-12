# @knowhere/sdk-typescript

Knowhere TypeScript SDK，提供类型安全的 API 客户端。

## 安装

```bash
pnpm add @knowhere/sdk-typescript
```

## 使用方式

```typescript
import { KnowhereClient } from '@knowhere/sdk-typescript';
import type { User } from '@knowhere/sdk-typescript';

// 创建客户端
const client = new KnowhereClient({
  baseUrl: 'http://localhost:5006/api',
  apiKey: 'your-api-key', // 可选
  timeout: 30000,
});

// 使用客户端
async function example() {
  try {
    // GET 请求
    const response = await client.get<User>('/users/123');
    console.log(response.data);

    // POST 请求
    const newUser = await client.post<User>('/users', {
      name: 'John Doe',
      email: 'john@example.com',
    });
    console.log(newUser.data);

  } catch (error) {
    console.error('API 请求失败:', error);
  }
}
```

## API

### KnowhereClient

#### 构造函数

```typescript
new KnowhereClient(config: KnowhereClientConfig)
```

#### 方法

- `get<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>>`
- `post<T>(endpoint: string, data?: any, options?: RequestInit): Promise<ApiResponse<T>>`
- `put<T>(endpoint: string, data?: any, options?: RequestInit): Promise<ApiResponse<T>>`
- `delete<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>>`
- `patch<T>(endpoint: string, data?: any, options?: RequestInit): Promise<ApiResponse<T>>`

## 类型安全

SDK 自动包含从 FastAPI 生成的 TypeScript 类型，确保 API 调用的类型安全。
