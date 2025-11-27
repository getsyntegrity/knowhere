import { NextResponse } from 'next/server'

/**
 * 运行时配置 API
 * 返回应用配置，支持不同环境动态配置
 */
export async function GET() {
  // 从环境变量读取配置（运行时读取，支持动态配置）
  // 使用不带 NEXT_PUBLIC_ 前缀的变量，支持运行时动态设置
  const config = {
    companyName: process.env.COMPANY_NAME || 'Knowhere AI',
    simpleCompanyName: process.env.SIMPLE_COMPANY_NAME || '',
    icpNumber: process.env.ICP_NUMBER || '',
    icpUrl: process.env.ICP_URL || 'https://beian.miit.gov.cn/',
    copyrightYear: new Date().getFullYear(),
  }

  return NextResponse.json({
    ...config,
    showIcp: !!config.icpNumber,
  })
}

