/**
 * 应用配置
 * 支持运行时动态配置（通过 API 获取）或环境变量
 * 
 * 优先级：
 * 1. 运行时 API 配置（如果可用）
 * 2. 环境变量（COMPANY_NAME 等，不带 NEXT_PUBLIC_ 前缀）
 * 3. 默认值
 */

// 默认配置（用于 SSR 和服务端）
export const getDefaultConfig = () => ({
  // 公司名称（运行时配置，不带 NEXT_PUBLIC_ 前缀）
  companyName: process.env.COMPANY_NAME || 'Knowhere AI',

  // 公司简称
  simpleCompanyName: process.env.SIMPLE_COMPANY_NAME || '',
  
  // ICP备案号（国内部署时使用）
  icpNumber: process.env.ICP_NUMBER || '',
  
  // ICP备案链接（国内部署时使用）
  icpUrl: process.env.ICP_URL || 'https://beian.miit.gov.cn/',
  
  // 版权年份
  copyrightYear: new Date().getFullYear(),
  
  // 是否显示ICP备案信息
  showIcp: !!process.env.ICP_NUMBER,
})

// 兼容旧的导出方式（使用默认配置）
export const AppConfig = getDefaultConfig()

// 运行时配置类型
export interface AppConfigType {
  companyName: string
  simpleCompanyName: string
  icpNumber: string
  icpUrl: string
  copyrightYear: number
  showIcp: boolean
}

// 获取运行时配置（客户端使用）
let runtimeConfig: AppConfigType | null = null
let configPromise: Promise<AppConfigType> | null = null

export async function getRuntimeConfig(): Promise<AppConfigType> {
  // 如果已有缓存，直接返回
  if (runtimeConfig) {
    return runtimeConfig
  }

  // 如果正在请求中，返回同一个 Promise
  if (configPromise) {
    return configPromise
  }

  // 在服务端，直接返回默认配置
  if (typeof window === 'undefined') {
    return getDefaultConfig()
  }

  // 在客户端，从 API 获取配置（使用 /config 避免被 rewrites 重写）
  configPromise = fetch('/config')
    .then(res => res.json())
    .then(config => {
      runtimeConfig = config
      return config
    })
    .catch(error => {
      console.warn('Failed to fetch runtime config, using default:', error)
      // 如果 API 失败，使用默认配置
      const defaultConfig = getDefaultConfig()
      runtimeConfig = defaultConfig
      return defaultConfig
    })
    .finally(() => {
      configPromise = null
    })

  return configPromise
}

