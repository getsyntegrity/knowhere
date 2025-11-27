/**
 * 应用配置
 * 从环境变量读取配置，提供默认值
 */

export const AppConfig = {
  // 公司名称
  companyName: process.env.NEXT_PUBLIC_COMPANY_NAME || 'Knowhere AI',

  // 公司简称
  simpleCompanyName: process.env.NEXT_PUBLIC_SIMPLE_COMPANY_NAME || '',
  
  // ICP备案号（国内部署时使用）
  icpNumber: process.env.NEXT_PUBLIC_ICP_NUMBER || '',
  
  // ICP备案链接（国内部署时使用）
  icpUrl: process.env.NEXT_PUBLIC_ICP_URL || '',
  
  // 版权年份
  copyrightYear: new Date().getFullYear(),
  
  // 是否显示ICP备案信息
  showIcp: !!process.env.NEXT_PUBLIC_ICP_NUMBER,
} as const

