// OAuth配置（从Context获取，不再使用NEXT_PUBLIC_环境变量）
// 注意：这些配置现在通过ConfigProvider在运行时传递

// 判断是否启用Google OAuth（仅检查配置是否存在）
export function isGoogleOAuthEnabled(googleClientId: string): boolean {
  return googleClientId !== ''
}

// GitHub OAuth URL生成
export function getGitHubAuthUrl() {
  const params = new URLSearchParams({
    client_id: OAUTH_CONFIG.github.clientId,
    redirect_uri: `${window.location.origin}/auth/callback/github`,
    scope: OAUTH_CONFIG.github.scope,
    state: generateRandomState(),
  })
  
  return `https://github.com/login/oauth/authorize?${params.toString()}`
}

// Apple OAuth URL生成
export function getAppleAuthUrl() {
  const params = new URLSearchParams({
    client_id: OAUTH_CONFIG.apple.clientId,
    redirect_uri: `${window.location.origin}/auth/callback/apple`,
    response_type: 'code id_token',
    scope: OAUTH_CONFIG.apple.scope,
    response_mode: 'form_post',
    state: generateRandomState(),
  })
  
  return `https://appleid.apple.com/auth/authorize?${params.toString()}`
}

// 生成随机状态字符串
function generateRandomState(): string {
  return Math.random().toString(36).substring(2, 15) + 
         Math.random().toString(36).substring(2, 15)
}

// 处理OAuth回调
export function handleOAuthCallback(provider: 'google' | 'apple' | 'github'): string | null {
  const urlParams = new URLSearchParams(window.location.search)
  
  if (provider === 'github') {
    return urlParams.get('code')
  } else if (provider === 'apple') {
    // Apple使用form_post，需要从document中获取
    const form = document.querySelector('form[action*="apple"]') as HTMLFormElement
    if (form) {
      const formData = new FormData(form)
      return formData.get('code') as string
    }
  }
  
  return null
}

// 验证OAuth状态
export function validateOAuthState(state: string): boolean {
  const savedState = localStorage.getItem('oauth_state')
  return savedState === state
}

// 保存OAuth状态
export function saveOAuthState(state: string): void {
  localStorage.setItem('oauth_state', state)
}

// 清除OAuth状态
export function clearOAuthState(): void {
  localStorage.removeItem('oauth_state')
}
