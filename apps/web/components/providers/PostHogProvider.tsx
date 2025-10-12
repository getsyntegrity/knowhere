'use client'

import { useEffect } from 'react'
import { usePathname } from 'next/navigation'
import { initPostHog, trackPageView } from '@/lib/posthog'

interface PostHogProviderProps {
  children: React.ReactNode
}

export default function PostHogProvider({ children }: PostHogProviderProps) {
  const pathname = usePathname()

  useEffect(() => {
    // 初始化 PostHog
    initPostHog()
  }, [])

  useEffect(() => {
    // 追踪页面浏览
    trackPageView(pathname)
  }, [pathname])

  return <>{children}</>
}
