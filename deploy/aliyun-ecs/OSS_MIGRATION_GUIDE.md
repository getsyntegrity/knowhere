# OSS存储迁移指南

## 概述

项目中使用了AWS S3进行对象存储，迁移到阿里云ECS需要改用OSS（Object Storage Service）。本文档详细说明需要修改的内容。

---

## 一、需要修改的文件清单

### 1. 核心配置文件（2个文件）

#### 1.1 `apps/api/app/core/config/storage.py`
- **文件作用**: 存储配置和S3客户端初始化
- **修改量**: 中（需要重写）
- **修改内容**:
  - 替换`boto3`为`oss2`
  - 修改环境变量名称（S3_XXX → OSS_XXX）
  - 重写`get_s3_client()`方法为`get_oss_client()`

#### 1.2 `apps/api/app/env.example`
- **文件作用**: 环境变量模板
- **修改量**: 小（只需替换变量名）
- **修改内容**:
  - `S3_BUCKET_NAME` → `OSS_BUCKET_NAME`
  - `S3_ACCESS_KEY_ID` → `OSS_ACCESS_KEY_ID`
  - `S3_SECRET_ACCESS_KEY` → `OSS_SECRET_ACCESS_KEY`
  - `S3_ENDPOINT_URL` → `OSS_ENDPOINT_URL`
  - `S3_REGION` → `OSS_REGION`
  - 保留其他S3相关配置用于兼容

### 2. 工具类文件（2个文件）

#### 2.1 `apps/api/app/utils/S3Utiles.py`
- **文件作用**: S3文件操作工具（文件夹创建、删除、列表）
- **修改量**: 中（所有方法需要重写）
- **主要方法**:
  - `create_folder()` - 创建文件夹
  - `delete_folder()` - 删除文件夹
  - `list_files_in_folder()` - 列出文件夹文件
- **修改内容**: 将boto3 API调用替换为oss2 API调用

#### 2.2 `apps/api/app/utils/FileDownUpUtils.py`
- **文件作用**: 文件上传下载工具
- **修改量**: 中（核心函数需要重写）
- **主要方法**:
  - `s3_upload_file()` - 上传文件
  - `s3_download_extract_zip()` - 下载并解压ZIP
  - `s3_public_file_url()` - 生成公网URL
  - `download_and_upload_image()` - 下载并上传图片
- **修改内容**: 将boto3操作替换为oss2操作

### 3. 服务类文件（1个文件）

#### 3.1 `apps/api/app/services/storage/file_upload_service.py`
- **文件作用**: 文件上传服务类
- **修改量**: 中（核心方法需要修改）
- **主要方法**:
  - `handle_direct_upload()` - 处理直传
  - `handle_url_upload()` - 处理URL上传
  - `generate_upload_url()` - 生成预签名URL
  - `download_from_s3()` - 从S3下载文件
  - `_upload_to_s3()` - 上传到S3
  - `_ensure_bucket_exists_async()` - 确保桶存在
- **修改内容**: 将s3_client替换为oss客户端

### 4. 引用文件（约10个文件，自动适配）

这些文件调用了上述工具类和服务类，通常**无需修改**，但需要确保：
- 环境变量已更新
- 配置已正确加载

---

## 二、详细修改说明

### 修改1: 依赖包添加

**文件**: `apps/api/requirements.txt`

**修改内容**:
```txt
# 删除
boto3

# 添加
oss2>=2.18.0
```

### 修改2: 配置文件重写

**文件**: `apps/api/app/core/config/storage.py`

**原代码结构**:
```python
import boto3
from botocore.config import Config

class StorageConfig(BaseModel):
    S3_BUCKET_NAME: str
    S3_ACCESS_KEY_ID: str
    S3_SECRET_ACCESS_KEY: str
    S3_ENDPOINT_URL: str
    
    def get_s3_client(self):
        return boto3.client(...)
```

**新代码结构**:
```python
import oss2
from oss2 import Auth, Bucket

class StorageConfig(BaseModel):
    OSS_BUCKET_NAME: str
    OSS_ACCESS_KEY_ID: str
    OSS_SECRET_ACCESS_KEY: str
    OSS_ENDPOINT: str  # 例如: oss-cn-hangzhou.aliyuncs.com
    
    def get_oss_bucket(self):
        auth = Auth(self.OSS_ACCESS_KEY_ID, self.OSS_SECRET_ACCESS_KEY)
        return Bucket(auth, self.OSS_ENDPOINT, self.OSS_BUCKET_NAME)
```

**关键差异**:
- boto3返回client对象，oss2返回Bucket对象
- 配置参数数量更少（OSS更简单）
- 不需要region配置（endpoint中已包含）

### 修改3: 环境变量更新

**文件**: `apps/api/.env` 或 `apps/api/env.example`

**修改对比**:
```bash
# AWS S3配置（原）
S3_BUCKET_NAME=your-bucket
S3_ACCESS_KEY_ID=your-access-key
S3_SECRET_ACCESS_KEY=your-secret-key
S3_ENDPOINT_URL=https://s3.amazonaws.com
S3_REGION=us-east-1

# 阿里云OSS配置（新）
OSS_BUCKET_NAME=your-bucket
OSS_ACCESS_KEY_ID=your-access-key
OSS_SECRET_ACCESS_KEY=your-secret-key
OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
# OSS不需要单独的region配置
```

### 修改4: API调用差异对照

#### 4.1 上传文件

**AWS S3**:
```python
import boto3
s3_client = boto3.client('s3')
s3_client.upload_file(local_path, bucket, key)
s3_client.upload_fileobj(file_obj, bucket, key)
```

**阿里云OSS**:
```python
import oss2
auth = oss2.Auth(access_key, secret_key)
bucket = oss2.Bucket(auth, endpoint, bucket_name)
bucket.put_object(key, data)
# 或
bucket.put_object_from_file(key, local_path)
```

#### 4.2 下载文件

**AWS S3**:
```python
s3_client.download_file(bucket, key, local_path)
s3_client.download_fileobj(bucket, key, file_obj)
```

**阿里云OSS**:
```python
bucket.get_object_to_file(key, local_path)
# 或
result = bucket.get_object(key)
data = result.read()
```

#### 4.3 删除文件

**AWS S3**:
```python
s3_client.delete_object(Bucket=bucket, Key=key)
```

**阿里云OSS**:
```python
bucket.delete_object(key)
```

#### 4.4 列出文件

**AWS S3**:
```python
response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
for obj in response.get('Contents', []):
    key = obj['Key']
```

**阿里云OSS**:
```python
for obj in oss2.ObjectIterator(bucket, prefix=prefix):
    key = obj.key
```

#### 4.5 生成预签名URL

**AWS S3**:
```python
url = s3_client.generate_presigned_url(
    'get_object',
    Params={'Bucket': bucket, 'Key': key},
    ExpiresIn=3600
)
```

**阿里云OSS**:
```python
url = bucket.sign_url('GET', key, 3600)
```

---

## 三、具体修改示例

### 示例1: `apps/api/app/utils/S3Utiles.py` → `OSSUtils.py`

**创建文件夹**:
```python
# 原代码（S3）
s3_client.put_object(
    Bucket=settings.S3_BUCKET_NAME,
    Key=folder_path,
    Body=b''
)

# 新代码（OSS）
bucket = settings.get_oss_bucket()
bucket.put_object(folder_path, b'')
```

**删除文件夹**:
```python
# 原代码（S3）
paginator = s3_client.get_paginator('list_objects_v2')
pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
for page in pages:
    if 'Contents' in page:
        for obj in page['Contents']:
            objects_to_delete.append({'Key': obj['Key']})
s3_client.delete_objects(Bucket=bucket, Delete={'Objects': objects_to_delete})

# 新代码（OSS）
bucket = settings.get_oss_bucket()
for obj in oss2.ObjectIterator(bucket, prefix=prefix):
    bucket.delete_object(obj.key)
```

### 示例2: `apps/api/app/utils/FileDownUpUtils.py`

**上传文件**:
```python
# 原代码（S3）
s3_client.upload_fileobj(
    file.file,
    settings.S3_BUCKET_NAME,
    object_key
)

# 新代码（OSS）
bucket = settings.get_oss_bucket()
bucket.put_object(object_key, file.file.read())
```

### 示例3: `apps/api/app/services/storage/file_upload_service.py`

**初始化客户端**:
```python
# 原代码
def __init__(self):
    self.s3_client = settings.get_s3_client()
    
# 新代码
def __init__(self):
    self.bucket = settings.get_oss_bucket()
```

**上传文件**:
```python
# 原代码
def _upload():
    self.s3_client.upload_file(local_file_path, bucket, s3_key)

# 新代码
def _upload():
    self.bucket.put_object_from_file(key, local_file_path)
```

---

## 四、环境变量完整对照

### 开发环境（MinIO）

**原配置**:
```bash
S3_BUCKET_NAME=knowhere
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin123
S3_ENDPOINT_URL=http://localhost:9000
S3_USE_SSL=false
S3_ADDRESSING_STYLE=path
```

**新配置（仍然可以兼容MinIO，无需修改）**:
```bash
# 如果继续使用MinIO（阿里云OSS兼容S3协议）
OSS_BUCKET_NAME=knowhere
OSS_ACCESS_KEY_ID=minioadmin
OSS_SECRET_ACCESS_KEY=minioadmin123
OSS_ENDPOINT=http://localhost:9000
```

### 生产环境（阿里云OSS）

**新配置**:
```bash
OSS_BUCKET_NAME=knowhere-production
OSS_ACCESS_KEY_ID=LTAI5txxxxxxxxxx
OSS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxx
OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
```

---

## 五、迁移步骤

### 步骤1: 安装OSS SDK（2分钟）

```bash
cd apps/api
pip install oss2>=2.18.0
# 或添加到requirements.txt
```

### 步骤2: 更新环境变量（5分钟）

编辑`.env`文件，添加OSS配置：
```bash
# 保留S3配置用于兼容（可选）
# 添加OSS配置
OSS_BUCKET_NAME=your-bucket
OSS_ACCESS_KEY_ID=your-key
OSS_SECRET_ACCESS_KEY=your-secret
OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
```

### 步骤3: 修改配置类（15分钟）

修改`apps/api/app/core/config/storage.py`:
- 添加OSS环境变量定义
- 实现`get_oss_bucket()`方法
- 保持向后兼容（可选）

### 步骤4: 重写工具类（1-2小时）

重写以下文件：
- `apps/api/app/utils/S3Utiles.py` → 重命名为`OSSUtils.py`或保持原名
- `apps/api/app/utils/FileDownUpUtils.py`
- `apps/api/app/services/storage/file_upload_service.py`

### 步骤5: 测试验证（30分钟）

```bash
# 测试文件上传
curl -X POST http://localhost:5005/api/v1/upload \
  -F "file=@test.pdf"

# 测试文件下载
curl http://localhost:5005/api/v1/download?key=test.pdf

# 验证OSS中有文件
# 在阿里云控制台查看
```

---

## 六、关键注意事项

### 1. OSS和S3的主要差异

| 特性 | S3 | OSS |
|------|-----|-----|
| **API协议** | RESTful | RESTful（兼容S3）|
| **SDK** | boto3 | oss2 |
| **Bucket操作** | client方法 | Bucket对象方法 |
| **错误处理** | ClientError | OssError |
| **分页** | 自动分页 | 手动迭代 |
| **URL生成** | generate_presigned_url | sign_url |

### 2. 配置项简化

OSS相比S3配置更简单：
- 不需要`addressing_style`
- 不需要`use_ssl`（自动HTTPS）
- region包含在endpoint中
- 重试策略内部处理

### 3. 向后兼容策略

**建议**: 在配置类中同时支持S3和OSS，通过环境变量切换：

```python
def get_storage_client(self):
    """获取存储客户端（自动适配S3或OSS）"""
    if self.USE_OSS:  # 环境变量控制
        return self.get_oss_bucket()
    else:
        return self.get_s3_client()
```

### 4. 文件路径处理

OSS和S3在路径处理上**完全相同**：
- 使用`/`作为分隔符
- 支持前缀路径
- Key不能以`/`开头

### 5. 桶（Bucket）命名

- S3: bucket名称全局唯一
- OSS: bucket名称全局唯一
- **注意**: 创建桶后无法修改名称

---

## 七、测试检查清单

### 功能测试
- [ ] 文件上传成功
- [ ] 文件下载成功
- [ ] 文件删除成功
- [ ] 列出文件成功
- [ ] 创建文件夹成功
- [ ] 删除文件夹成功
- [ ] 生成预签名URL成功

### 错误处理测试
- [ ] 文件不存在时的处理
- [ ] 认证失败的处理
- [ ] 网络超时的处理
- [ ] 存储空间不足的处理

### 性能测试
- [ ] 大文件上传（>100MB）
- [ ] 并发上传
- [ ] 大批量文件操作

### 兼容性测试
- [ ] 不同文件类型（PDF、DOCX、图片等）
- [ ] 中文文件名
- [ ] 特殊字符文件名

---

## 八、预计工作量

| 任务 | 难度 | 时间 |
|------|------|------|
| 安装OSS SDK | ⭐ 易 | 5分钟 |
| 更新环境变量 | ⭐ 易 | 10分钟 |
| 重写配置类 | ⭐⭐ 中 | 30分钟 |
| 重写工具类 | ⭐⭐⭐ 难 | 2-3小时 |
| 重写服务类 | ⭐⭐⭐ 难 | 1-2小时 |
| 测试验证 | ⭐⭐ 中 | 1小时 |
| **总计** | | **4-6小时** |

---

## 九、参考资料

- [阿里云OSS官方文档](https://help.aliyun.com/product/31815.html)
- [OSS Python SDK文档](https://help.aliyun.com/document_detail/32026.html)
- [OSS API参考](https://help.aliyun.com/document_detail/31947.html)
- [项目S3使用示例](../apps/api/app/utils/S3Utiles.py)

---

**总结**: 迁移OSS主要是替换SDK和API调用，概念和用法相似，工作量主要集中在工具类的重写上。

