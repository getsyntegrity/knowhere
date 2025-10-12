#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

console.log('🚀 开始生成类型定义...');

// 1. 从 FastAPI 导出 OpenAPI schema
console.log('📦 导出 FastAPI OpenAPI schema...');
try {
  execSync('cd ../../apps/api && python scripts/export_openapi.py', { stdio: 'inherit' });
  console.log('✅ OpenAPI schema 导出成功');
} catch (error) {
  console.error('❌ 导出 OpenAPI schema 失败:', error.message);
  process.exit(1);
}

// 2. 检查 openapi.json 是否存在
const openapiPath = path.resolve(__dirname, '../../apps/api/openapi.json');
if (!fs.existsSync(openapiPath)) {
  console.error('❌ 找不到 openapi.json 文件:', openapiPath);
  process.exit(1);
}

// 3. 确保 shared-types 目录存在
const sharedTypesDir = path.resolve(__dirname, '../shared-types/generated');
if (!fs.existsSync(sharedTypesDir)) {
  fs.mkdirSync(sharedTypesDir, { recursive: true });
  console.log('📁 创建 shared-types/generated 目录');
}

// 4. 生成 TypeScript 类型
console.log('🔨 生成 TypeScript 类型...');
const outputPath = path.resolve(sharedTypesDir, 'api-types.ts');

try {
  execSync(`npx openapi-typescript ${openapiPath} -o ${outputPath}`, { stdio: 'inherit' });
  console.log('✅ TypeScript 类型生成成功');
} catch (error) {
  console.error('❌ 生成 TypeScript 类型失败:', error.message);
  process.exit(1);
}

// 5. 生成 Python 类型（可选）
console.log('🐍 生成 Python 类型...');
const pythonOutputDir = path.resolve(__dirname, '../sdk-python/knowhere_sdk/generated');
if (!fs.existsSync(pythonOutputDir)) {
  fs.mkdirSync(pythonOutputDir, { recursive: true });
}

try {
  // 使用 datamodel-code-generator 生成 Python 模型
  execSync(`npx datamodel-code-generator --input ${openapiPath} --input-file-type openapi --output ${pythonOutputDir}/models.py --output-model-type pydantic_v2.BaseModel`, { stdio: 'inherit' });
  console.log('✅ Python 类型生成成功');
} catch (error) {
  console.warn('⚠️  Python 类型生成失败（可选）:', error.message);
}

console.log('🎉 类型生成完成！');
console.log(`📄 TypeScript 类型: ${outputPath}`);
console.log(`🐍 Python 类型: ${pythonOutputDir}/models.py`);
