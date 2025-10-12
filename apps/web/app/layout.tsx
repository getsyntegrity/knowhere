import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { ThemeProvider } from '@/components/theme-provider'
import PostHogProvider from '@/components/providers/PostHogProvider'
import { Providers } from '@/components/providers/Providers'

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
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className={inter.className}>
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
      </body>
    </html>
  )
}
