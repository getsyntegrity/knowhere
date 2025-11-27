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
    NEXT_PUBLIC_COMPANY_NAME: process.env.NEXT_PUBLIC_COMPANY_NAME || '',
    NEXT_PUBLIC_SIMPLE_COMPANY_NAME: process.env.NEXT_PUBLIC_SIMPLE_COMPANY_NAME || '',
    NEXT_PUBLIC_ICP_NUMBER: process.env.NEXT_PUBLIC_ICP_NUMBER || '',
    NEXT_PUBLIC_ICP_URL: process.env.NEXT_PUBLIC_ICP_URL || '',
  },
}

module.exports = nextConfig
