import Link from 'next/link'

export default function DocsHome() {
  return (
    <main className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold text-center mb-8">
          Knowhere 文档
        </h1>
        
        <div className="prose max-w-none">
          <p className="text-xl text-muted-foreground text-center mb-12">
            AI 知识库管理系统的完整文档和 API 参考
          </p>

          <div className="grid md:grid-cols-2 gap-8">
            <div className="bg-card p-6 rounded-lg shadow-lg">
              <h2 className="text-2xl font-semibold mb-4">快速开始</h2>
              <ul className="space-y-2">
                <li>
                  <Link href="/getting-started" className="text-primary hover:underline">
                    安装和配置
                  </Link>
                </li>
                <li>
                  <Link href="/api/overview" className="text-primary hover:underline">
                    API 概览
                  </Link>
                </li>
                <li>
                  <Link href="/sdk/typescript" className="text-primary hover:underline">
                    TypeScript SDK
                  </Link>
                </li>
                <li>
                  <Link href="/sdk/python" className="text-primary hover:underline">
                    Python SDK
                  </Link>
                </li>
              </ul>
            </div>

            <div className="bg-card p-6 rounded-lg shadow-lg">
              <h2 className="text-2xl font-semibold mb-4">开发指南</h2>
              <ul className="space-y-2">
                <li>
                  <Link href="/development/setup" className="text-primary hover:underline">
                    开发环境搭建
                  </Link>
                </li>
                <li>
                  <Link href="/development/architecture" className="text-primary hover:underline">
                    架构设计
                  </Link>
                </li>
                <li>
                  <Link href="/development/contributing" className="text-primary hover:underline">
                    贡献指南
                  </Link>
                </li>
                <li>
                  <Link href="/api/reference" className="text-primary hover:underline">
                    API 参考
                  </Link>
                </li>
              </ul>
            </div>
          </div>

          <div className="mt-12 bg-muted p-6 rounded-lg">
            <h2 className="text-2xl font-semibold mb-4">API 状态</h2>
            <p className="text-muted-foreground">
              查看实时 API 状态和端点信息：
            </p>
            <div className="mt-4">
              <Link 
                href="/api/docs" 
                className="inline-block bg-primary text-primary-foreground px-6 py-2 rounded-md hover:bg-primary/90 transition-colors"
              >
                查看 API 文档
              </Link>
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}
