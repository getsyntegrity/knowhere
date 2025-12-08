// OAuth配置（从Context获取，不再使用NEXT_PUBLIC_环境变量）
// 注意：这些配置现在通过ConfigProvider在运行时传递

// 判断是否启用Google OAuth（仅检查配置是否存在）
export function isGoogleOAuthEnabled(googleClientId: string): boolean {
  return googleClientId !== ''
}

// 判断是否启用GitHub OAuth（仅检查配置是否存在）
export function isGitHubOAuthEnabled(githubClientId: string): boolean {
  return githubClientId !== ''
}

// 判断是否启用Apple OAuth（仅检查配置是否存在）
export function isAppleOAuthEnabled(appleClientId: string): boolean {
  return appleClientId !== ''
}

// GitHub OAuth URL生成
export function getGitHubAuthUrl(githubClientId: string) {
  const state = generateRandomState()
  saveOAuthState(state) // 保存state以便后续验证
  
  const params = new URLSearchParams({
    client_id: githubClientId,
    redirect_uri: `${window.location.origin}/auth/callback/github`,
    scope: 'user:email', // 需要user:email scope以获取用户邮箱
    state: state,
  })
  
  return `https://github.com/login/oauth/authorize?${params.toString()}`
}

// Apple OAuth URL生成
export function getAppleAuthUrl(appleClientId: string) {
  const state = generateRandomState()
  saveOAuthState(state) // 保存state以便后续验证
  
  const params = new URLSearchParams({
    client_id: appleClientId,
    redirect_uri: `${window.location.origin}/auth/callback/apple`,
    response_type: 'code id_token',
    scope: 'name email',
    response_mode: 'form_post',
    state: state,
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
