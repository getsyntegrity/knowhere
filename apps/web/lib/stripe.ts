/**
 * Stripe客户端配置
 */
import { loadStripe, Stripe } from '@stripe/stripe-js'

let stripePromise: Promise<Stripe | null>

export const getStripe = () => {
  if (!stripePromise) {
    const publishableKey = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY
    
    if (!publishableKey) {
      throw new Error('NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY is not defined')
    }
    
    stripePromise = loadStripe(publishableKey)
  }
  
  return stripePromise
}

// 定价常量
export const CREDITS_UNIT_PRICE = 0.02 // 每个Credit 0.02元
export const MIN_CREDITS_PURCHASE = 100 // 最小购买100 Credits

// 快捷金额选项(作为输入参考)
export const quickAmounts = [
  { credits: 500, amount: 10 },   // ¥10
  { credits: 2500, amount: 50 },  // ¥50
  { credits: 5000, amount: 100 }, // ¥100
  { credits: 25000, amount: 500 } // ¥500
]

// 计算Credits对应的金额(人民币)
export const calculateCreditsAmount = (credits: number): number => {
  return Math.round(credits * CREDITS_UNIT_PRICE * 100) / 100
}

// 验证Credits数量
export const validateCreditsAmount = (credits: number): boolean => {
  return credits >= MIN_CREDITS_PURCHASE && Number.isInteger(credits)
}
