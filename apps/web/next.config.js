/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/api/:path*',  // 所有 /api/* 请求转发到外部 API
        destination: process.env.NEXT_PUBLIC_API_URL ? `${process.env.NEXT_PUBLIC_API_URL}/:path*` : 'https://apitest.knowhereto.ai/:path*',
      },
    ]
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'https://apitest.knowhereto.ai',
    // 注意：其他配置（公司名称、ICP等）通过服务端组件在运行时读取环境变量
    // 支持动态配置，无需在构建时固定，无需 NEXT_PUBLIC_ 前缀
  },
}

module.exports = nextConfig
