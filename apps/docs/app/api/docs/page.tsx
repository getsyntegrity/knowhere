'use client'

import { useState, useEffect } from 'react'
import { KnowhereClient } from '@knowhere/sdk-typescript'

export default function ApiDocs() {
  const [openapiSpec, setOpenapiSpec] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadOpenApiSpec()
  }, [])

  const loadOpenApiSpec = async () => {
    try {
      const client = new KnowhereClient({
        baseUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5006/api',
      })
      
      // 获取 OpenAPI spec
      const response = await client.get('/openapi.json')
      setOpenapiSpec(response.data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <main className="container mx-auto px-4 py-8">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
          <p>加载 API 文档中...</p>
        </div>
      </main>
    )
  }

  if (error) {
    return (
      <main className="container mx-auto px-4 py-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-destructive mb-4">加载失败</h1>
          <p className="text-muted-foreground mb-4">{error}</p>
          <button
            onClick={loadOpenApiSpec}
            className="bg-primary text-primary-foreground px-4 py-2 rounded-md hover:bg-primary/90"
          >
            重试
          </button>
        </div>
      </main>
    )
  }

  if (!openapiSpec) {
    return (
      <main className="container mx-auto px-4 py-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-4">API 文档</h1>
          <p className="text-muted-foreground">未找到 API 规范</p>
        </div>
      </main>
    )
  }

  return (
    <main className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-4xl font-bold mb-8">{openapiSpec.info?.title || 'API 文档'}</h1>
        
        {openapiSpec.info?.description && (
          <p className="text-xl text-muted-foreground mb-8">{openapiSpec.info.description}</p>
        )}

        <div className="bg-card p-6 rounded-lg shadow-lg mb-8">
          <h2 className="text-2xl font-semibold mb-4">基本信息</h2>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <strong>版本:</strong> {openapiSpec.info?.version || 'N/A'}
            </div>
            <div>
              <strong>服务器:</strong> {openapiSpec.servers?.[0]?.url || 'N/A'}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <h2 className="text-3xl font-semibold">API 端点</h2>
          
          {Object.entries(openapiSpec.paths || {}).map(([path, methods]: [string, any]) => (
            <div key={path} className="bg-card p-6 rounded-lg shadow-lg">
              <h3 className="text-xl font-semibold mb-4">{path}</h3>
              
              <div className="space-y-4">
                {Object.entries(methods).map(([method, spec]: [string, any]) => (
                  <div key={method} className="border-l-4 border-primary pl-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`px-2 py-1 rounded text-sm font-mono ${
                        method === 'get' ? 'bg-green-100 text-green-800' :
                        method === 'post' ? 'bg-blue-100 text-blue-800' :
                        method === 'put' ? 'bg-yellow-100 text-yellow-800' :
                        method === 'delete' ? 'bg-red-100 text-red-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {method.toUpperCase()}
                      </span>
                      <span className="font-semibold">{spec.summary || 'No summary'}</span>
                    </div>
                    
                    {spec.description && (
                      <p className="text-muted-foreground text-sm mb-2">{spec.description}</p>
                    )}
                    
                    {spec.parameters && spec.parameters.length > 0 && (
                      <div className="text-sm">
                        <strong>参数:</strong>
                        <ul className="list-disc list-inside ml-4">
                          {spec.parameters.map((param: any, index: number) => (
                            <li key={index}>
                              <code>{param.name}</code> ({param.in}) - {param.description || 'No description'}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  )
}
