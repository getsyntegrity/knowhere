/**
 * 应用配置
 * 从环境变量读取配置，提供默认值
 */

export const AppConfig = {
  // 公司名称
  companyName: process.env.NEXT_PUBLIC_COMPANY_NAME || '深圳市渊维科技有限公司',
  
  // ICP备案号（国内部署时使用）
  icpNumber: process.env.NEXT_PUBLIC_ICP_NUMBER || '',
  
  // ICP备案链接（国内部署时使用）
  icpUrl: process.env.NEXT_PUBLIC_ICP_URL || 'https://beian.miit.gov.cn/',
  
  // 版权年份
  copyrightYear: new Date().getFullYear(),
  
  // 是否显示ICP备案信息
  showIcp: !!process.env.NEXT_PUBLIC_ICP_NUMBER,
} as const

