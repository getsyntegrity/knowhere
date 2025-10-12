# @knowhere/shared-types

共享的 TypeScript 类型定义包，包含从 FastAPI OpenAPI schema 自动生成的 API 类型。

## 使用方式

```typescript
import type { paths, components } from '@knowhere/shared-types';

// 使用 API 路径类型
type UserEndpoint = paths['/api/v1/users/{user_id}']['get'];

// 使用组件类型
type User = components['schemas']['User'];
```

## 生成类型

类型定义通过 `pnpm generate:types` 命令自动生成，无需手动维护。

## 文件结构

```
shared-types/
├── generated/
│   └── api-types.ts    # 自动生成的 OpenAPI TypeScript 类型
└── package.json
```
