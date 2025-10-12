import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

// 需要认证的路径
const protectedPaths = ['/dashboard', '/api-keys', '/billing', '/settings']

// 认证相关路径
const authPaths = ['/login', '/register']

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // 检查是否访问受保护的路径
  const isProtectedPath = protectedPaths.some(path => pathname.startsWith(path))
  const isAuthPath = authPaths.some(path => pathname.startsWith(path))

  // 由于现在使用localStorage存储token，middleware无法直接检查
  // 改为在客户端layout组件中进行认证检查
  // 这里只做基础的路由保护，具体的认证状态由AuthContext管理
  
  // 对于受保护路径，让客户端处理认证检查
  // 对于认证页面，也由客户端处理重定向逻辑
  
  return NextResponse.next()
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api (API routes)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    '/((?!api|_next/static|_next/image|favicon.ico).*)',
  ],
}
