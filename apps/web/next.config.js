/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: process.env.NEXT_PUBLIC_API_URL ? `${process.env.NEXT_PUBLIC_API_URL}/:path*` : 'https://apitest.knowhereto.ai/:path*',
      },
    ]
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'https://apitest.knowhereto.ai',
    // 注意：其他配置（公司名称、ICP等）现在通过运行时 API (/api/config) 获取
    // 支持动态配置，无需在构建时固定
  },
}

module.exports = nextConfig
