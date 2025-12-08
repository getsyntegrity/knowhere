"use client"

import { AuthProvider } from '@/contexts/AuthContext'
import { Toaster } from '@/components/ui/sonner'
import { GoogleOAuthProvider } from '@react-oauth/google'
import { useAppConfigContext } from '@/components/providers/ConfigProvider'

export function Providers({ children }: { children: React.ReactNode }) {
  const config = useAppConfigContext()
  const googleClientId = config.googleClientId
  
  // 仅当配置了Google Client ID时初始化GoogleOAuthProvider
  const shouldEnableGoogle = googleClientId !== ''
  
  const content = (
    <AuthProvider>
      {children}
      <Toaster />
    </AuthProvider>
  )
  
  return shouldEnableGoogle ? (
    <GoogleOAuthProvider clientId={googleClientId}>
      {content}
    </GoogleOAuthProvider>
  ) : (
    content
  )
}
