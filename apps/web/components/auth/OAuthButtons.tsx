"use client"

import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { getGitHubAuthUrl, getAppleAuthUrl, isGoogleOAuthEnabled, isGitHubOAuthEnabled, isAppleOAuthEnabled } from '@/lib/oauth'
import { useAppConfigContext } from '@/components/providers/ConfigProvider'
import { Github, Apple } from 'lucide-react'
import { GoogleLogin } from '@react-oauth/google'

interface OAuthButtonsProps {
  onSuccess?: () => void
  onError?: (error: string) => void
}

export function OAuthButtons({ onSuccess, onError }: OAuthButtonsProps) {
  const { oauthLogin } = useAuth()
  const toast = useToast()
  const config = useAppConfigContext()
  
  // 从Context获取OAuth配置（运行时配置）
  const googleClientId = config.googleClientId
  const githubClientId = config.githubClientId
  const appleClientId = config.appleClientId
  const googleEnabled = isGoogleOAuthEnabled(googleClientId)
  const githubEnabled = isGitHubOAuthEnabled(githubClientId)
  const appleEnabled = isAppleOAuthEnabled(appleClientId)

  const handleOAuthSuccess = async (provider: 'google' | 'apple' | 'github', token: string) => {
    try {
      await oauthLogin(provider, token)
      toast.success(`${provider}登录成功`)
      onSuccess?.()
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '登录失败'
      toast.error(`${provider}登录失败`, errorMessage)
      onError?.(errorMessage)
    }
  }

  const handleGoogleSuccess = (credentialResponse: any) => {
    if (credentialResponse.credential) {
      handleOAuthSuccess('google', credentialResponse.credential)
    }
  }

  const handleGoogleError = () => {
    toast.error('Google登录失败')
    onError?.('Google登录失败')
  }

  const handleGitHubClick = () => {
    const authUrl = getGitHubAuthUrl(githubClientId)
    window.location.href = authUrl
  }

  const handleAppleClick = () => {
    const authUrl = getAppleAuthUrl(appleClientId)
    window.location.href = authUrl
  }

  return (
    <div className="space-y-3">
      {/* Google登录 - 仅当配置了Google Client ID时显示 */}
      {googleEnabled && (
        <GoogleLogin
          onSuccess={handleGoogleSuccess}
          onError={handleGoogleError}
          useOneTap
          theme="outline"
          size="large"
          width="100%"
          text="signin_with"
          shape="rectangular"
          logo_alignment="left"
        />
      )}

      {/* GitHub登录 - 仅当配置了GitHub Client ID时显示 */}
      {githubEnabled && (
        <Button
          variant="outline"
          onClick={handleGitHubClick}
          className="w-full h-11"
        >
          <Github className="w-5 h-5 mr-2" />
          使用 GitHub 继续
        </Button>
      )}

      {/* Apple登录 - 仅当配置了Apple Client ID时显示 */}
      {appleEnabled && (
        <Button
          variant="outline"
          onClick={handleAppleClick}
          className="w-full h-11"
        >
          <Apple className="w-5 h-5 mr-2" />
          使用 Apple 继续
        </Button>
      )}

      {/* 分隔线 */}
      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <span className="w-full border-t" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-background px-2 text-muted-foreground">
            或使用邮箱继续
          </span>
        </div>
      </div>
    </div>
  )
}
