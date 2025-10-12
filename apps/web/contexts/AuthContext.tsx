"use client"

import React, { createContext, useContext, useEffect, useState } from 'react'
import { api, type User } from '@/lib/api'
import { trackLogin, trackSignUp, identifyUser, resetUser } from '@/lib/posthog'


interface AuthContextType {
  user: User | null
  token: string | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, username: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
  oauthLogin: (provider: 'google' | 'apple' | 'github', token: string) => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const isAuthenticated = !!user && !!token


  // 从localStorage恢复token
  useEffect(() => {
    const savedToken = localStorage.getItem('auth_token')
    if (savedToken) {
      setToken(savedToken)
      // 同步更新API客户端的token
      api.updateToken(savedToken)
    }
    setIsLoading(false)
  }, [])

  // 当token变化时刷新用户信息
  useEffect(() => {
    if (token && !user) {
      refreshUser()
    }
  }, [token])

  // 添加token自动续期功能
  useEffect(() => {
    if (!token) return

    // 检查token是否即将过期（剩余1天时续期）
    const checkAndRenewToken = async () => {
      try {
        // 解析JWT token获取过期时间
        const payload = JSON.parse(atob(token.split('.')[1]))
        const exp = payload.exp * 1000 // 转换为毫秒
        const now = Date.now()
        const timeUntilExpiry = exp - now
        
        // 如果token在24小时内过期，尝试续期
        if (timeUntilExpiry < 24 * 60 * 60 * 1000 && timeUntilExpiry > 0) {
          console.log('Token即将过期，尝试续期...')
          const response = await api.renewToken()
          if (response.access_token) {
            setToken(response.access_token)
            api.updateToken(response.access_token)
            console.log('Token续期成功')
          }
        }
      } catch (error) {
        console.warn('Token续期失败:', error)
        // 续期失败时清除认证状态
        logout()
      }
    }

    // 延迟5秒后开始检查，避免在刚登录时立即检查
    const initialTimeout = setTimeout(checkAndRenewToken, 5000)

    // 每6小时检查一次
    const interval = setInterval(checkAndRenewToken, 6 * 60 * 60 * 1000)

    return () => {
      clearTimeout(initialTimeout)
      clearInterval(interval)
    }
  }, [token])

  const refreshUser = async () => {
    if (!token) return

    try {
      // 更新API客户端的token
      api.updateToken(token)
      const userData = await api.getCurrentUser()
      setUser(userData)
    } catch (error) {
      console.error('Failed to refresh user:', error)
      
      // 检查是否是认证错误
      if (error instanceof Error && (
        error.message.includes('Authentication required') ||
        error.message.includes('Token格式无效') ||
        error.message.includes('401')
      )) {
        console.warn('Token已过期或无效，正在清除认证状态')
        // 静默清除认证状态，不显示弹窗
        logout()
      } else {
        // 其他错误也清除认证状态
        logout()
      }
    }
  }

  const login = async (email: string, password: string) => {
    try {
      const response = await api.login({ email, password })
      
      if (response.access_token) {
        const accessToken = response.access_token
        setToken(accessToken)
        api.updateToken(accessToken)
        
        // 获取用户信息
        await refreshUser()
      } else {
        throw new Error('登录失败：未收到访问令牌')
      }
    } catch (error) {
      console.error('Login error:', error)
      throw error
    }
  }

  const register = async (email: string, password: string, username: string) => {
    try {
      const response = await api.register({ email, password, username })

      if (response) {
        // 注册成功后自动登录
        await login(email, password)
        
        // 追踪注册事件
        trackSignUp('email', user?.id || '')
      }
    } catch (error) {
      console.error('Register error:', error)
      throw error
    }
  }

  const oauthLogin = async (provider: 'google' | 'apple' | 'github', token: string) => {
    try {
      const response = await api.oauthLogin(provider, token)

      if (response.access_token) {
        const accessToken = response.access_token
        setToken(accessToken)
        api.updateToken(accessToken)
        
        // 设置用户信息
        if (response.user_info) {
          setUser(response.user_info)
        } else {
          // 如果没有用户信息，重新获取
          await refreshUser()
        }
      } else {
        throw new Error(`${provider}登录失败`)
      }
    } catch (error) {
      console.error(`${provider} login error:`, error)
      throw error
    }
  }

  const logout = () => {
    // 追踪登出事件
    resetUser()
    
    setUser(null)
    setToken(null)
    api.updateToken(null)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated,
        login,
        register,
        logout,
        refreshUser,
        oauthLogin,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
