"use client"

import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Check, Loader2 } from 'lucide-react'
import { SubscriptionPlan, Subscription } from '@/lib/api'
import { useToast } from '@/hooks/useToast'
import { api } from '@/lib/api'

interface SubscriptionCardProps {
  plan: SubscriptionPlan
  currentSubscription?: Subscription | null
  onSubscriptionChange?: () => void
}

export function SubscriptionCard({ 
  plan, 
  currentSubscription, 
  onSubscriptionChange 
}: SubscriptionCardProps) {
  const [isLoading, setIsLoading] = useState(false)
  const toast = useToast()
  
  const isCurrentPlan = currentSubscription?.plan_type === plan.id
  const isActive = currentSubscription?.status === 'active'
  
  const handleSubscribe = async () => {
    if (isCurrentPlan && isActive) {
      toast.info('您当前已订阅此套餐')
      return
    }
    
    try {
      setIsLoading(true)
      
      if (plan.id === 'free') {
        // 免费套餐不需要支付
        toast.info('免费套餐无需订阅')
        return
      }
      
      // 调用订阅API
      const response = await api.subscribePlan(plan.id)
      
      if (response.checkout_url) {
        // 跳转到Stripe Checkout
        window.location.href = response.checkout_url
      } else {
        throw new Error('获取支付链接失败')
      }
    } catch (error) {
      console.error('订阅失败:', error)
      toast.error('订阅失败，请稍后重试')
    } finally {
      setIsLoading(false)
    }
  }
  
  const getButtonText = () => {
    if (isLoading) return '处理中...'
    if (isCurrentPlan && isActive) return '当前套餐'
    if (plan.id === 'free') return '免费使用'
    return `订阅 ${plan.name}`
  }
  
  const getButtonVariant = () => {
    if (isCurrentPlan && isActive) return 'secondary'
    if (plan.popular) return 'default'
    return 'outline'
  }
  
  return (
    <Card className={`relative ${plan.popular ? 'border-primary shadow-lg' : ''}`}>
      {plan.popular && (
        <Badge className="absolute -top-2 left-1/2 transform -translate-x-1/2">
          推荐
        </Badge>
      )}
      
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">{plan.name}</CardTitle>
        <CardDescription>
          {plan.price === 0 ? (
            <span className="text-2xl font-bold text-green-600">免费</span>
          ) : (
            <span className="text-2xl font-bold">
              ¥{plan.price}
              <span className="text-sm font-normal text-muted-foreground">
                /{plan.period}
              </span>
            </span>
          )}
        </CardDescription>
      </CardHeader>
      
      <CardContent className="space-y-4">
        <div className="text-center">
          <div className="text-3xl font-bold text-primary">
            {plan.credits.toLocaleString()}
          </div>
          <div className="text-sm text-muted-foreground">Credits/月</div>
        </div>
        
        <ul className="space-y-2">
          {plan.features.map((feature, index) => (
            <li key={index} className="flex items-center gap-2">
              <Check className="h-4 w-4 text-green-500 flex-shrink-0" />
              <span className="text-sm">{feature}</span>
            </li>
          ))}
        </ul>
        
        <Button
          className="w-full"
          variant={getButtonVariant()}
          onClick={handleSubscribe}
          disabled={isLoading || (isCurrentPlan && isActive)}
        >
          {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {getButtonText()}
        </Button>
      </CardContent>
    </Card>
  )
}
