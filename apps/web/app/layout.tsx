import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { ThemeProvider } from '@/components/theme-provider'
import PostHogProvider from '@/components/providers/PostHogProvider'
import { Providers } from '@/components/providers/Providers'
import { ConfigProvider } from '@/components/providers/ConfigProvider'
import { getDefaultConfig } from '@/lib/config'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Knowhere - AI 知识库管理系统',
  description: '基于 AI 的知识库管理和智能问答系统',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // 在服务端读取环境变量（运行时配置，不带NEXT_PUBLIC_前缀）
  const appConfig = getDefaultConfig()

  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className={inter.className}>
        <ConfigProvider config={appConfig}>
          <ThemeProvider
            attribute="class"
            defaultTheme="system"
            enableSystem
            disableTransitionOnChange
          >
            <PostHogProvider>
              <Providers>
                <div className="min-h-screen bg-background">
                  {children}
                </div>
              </Providers>
            </PostHogProvider>
          </ThemeProvider>
        </ConfigProvider>
      </body>
    </html>
  )
}
