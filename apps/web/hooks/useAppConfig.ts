import { useState, useEffect } from 'react'
import { getRuntimeConfig, getDefaultConfig, type AppConfigType } from '@/lib/config'

/**
 * 获取应用配置的 Hook
 * 支持运行时动态配置
 */
export function useAppConfig(): AppConfigType {
  const [config, setConfig] = useState<AppConfigType>(getDefaultConfig())

  useEffect(() => {
    // 在客户端获取运行时配置
    getRuntimeConfig().then(setConfig)
  }, [])

  return config
}

