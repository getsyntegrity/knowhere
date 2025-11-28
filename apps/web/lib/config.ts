/**
 * 应用配置
 * 支持运行时动态配置（通过环境变量）
 * 
 * 实现方式：
 * - 在服务端组件（如 Layout）中调用 getDefaultConfig() 读取环境变量
 * - 通过 React Context 传递给客户端组件
 * - 环境变量（COMPANY_NAME 等，不带 NEXT_PUBLIC_ 前缀）在运行时读取
 * 
 * 优先级：
 * 1. 环境变量（COMPANY_NAME 等，不带 NEXT_PUBLIC_ 前缀）
 * 2. 默认值
 */

// 配置类型
export interface AppConfigType {
  companyName: string
  simpleCompanyName: string
  icpNumber: string
  icpUrl: string
  copyrightYear: number
  showIcp: boolean
}

// 获取配置（用于服务端组件）
// 在服务端组件中调用此函数读取环境变量，然后通过 ConfigProvider 传递给客户端组件
export const getDefaultConfig = (): AppConfigType => ({
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

