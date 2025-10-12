"use client"

import { useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { handleOAuthCallback, validateOAuthState, clearOAuthState } from '@/lib/oauth'

export default function AppleCallbackPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { oauthLogin } = useAuth()
  const toast = useToast()

  useEffect(() => {
    const handleCallback = async () => {
      try {
        const code = searchParams.get('code')
        const state = searchParams.get('state')

        if (!code) {
          throw new Error('未收到授权码')
        }

        if (state && !validateOAuthState(state)) {
          throw new Error('状态验证失败')
        }

        // 清理OAuth状态
        clearOAuthState()

        // 使用授权码进行OAuth登录
        await oauthLogin('apple', code)
        
        toast.success('Apple登录成功')
        router.push('/dashboard')
      } catch (error) {
        console.error('Apple OAuth callback error:', error)
        const errorMessage = error instanceof Error ? error.message : 'Apple登录失败'
        toast.error('Apple登录失败', errorMessage)
        router.push('/login')
      }
    }

    handleCallback()
  }, [searchParams, oauthLogin, toast, router])

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
        <p>正在处理Apple登录...</p>
      </div>
    </div>
  )
}
