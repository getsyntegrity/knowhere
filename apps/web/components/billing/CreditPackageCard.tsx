"use client"

import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Loader2, CreditCard, Zap } from 'lucide-react'
import { useToast } from '@/hooks/useToast'
import { StripeElements } from './StripeElements'
import { CreditPaymentForm } from './CreditPaymentForm'
import { 
  CREDITS_UNIT_PRICE, 
  MIN_CREDITS_PURCHASE, 
  quickAmounts, 
  calculateCreditsAmount, 
  validateCreditsAmount 
} from '@/lib/stripe'

export function CreditPackageCard() {
  const [creditsAmount, setCreditsAmount] = useState(MIN_CREDITS_PURCHASE)
  const [isValid, setIsValid] = useState(true)
  const [showPaymentForm, setShowPaymentForm] = useState(false)
  const toast = useToast()
  
  const calculatedAmount = calculateCreditsAmount(creditsAmount)
  
  useEffect(() => {
    setIsValid(validateCreditsAmount(creditsAmount))
  }, [creditsAmount])
  
  const handleCreditsChange = (value: string) => {
    const numValue = parseInt(value) || 0
    setCreditsAmount(numValue)
  }
  
  const handleQuickAmount = (credits: number) => {
    setCreditsAmount(credits)
  }
  
  const handlePurchase = () => {
    if (!isValid) {
      toast.error(`最少需要购买 ${MIN_CREDITS_PURCHASE} Credits`)
      return
    }
    
    setShowPaymentForm(true)
  }
  
  const handlePaymentSuccess = () => {
    setShowPaymentForm(false)
    toast.success(`成功购买 ${creditsAmount} Credits!`)
  }
  
  const handlePaymentCancel = () => {
    setShowPaymentForm(false)
  }
  
  if (showPaymentForm) {
    return (
      <StripeElements>
        <CreditPaymentForm
          creditsAmount={creditsAmount}
          amount={calculatedAmount}
          onSuccess={handlePaymentSuccess}
          onCancel={handlePaymentCancel}
        />
      </StripeElements>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Zap className="h-5 w-5" />
          购买Credits量包
        </CardTitle>
        <CardDescription>
          一次性购买Credits，30天内有效。先消耗订阅赠送的Credits，再消耗量包Credits。
        </CardDescription>
      </CardHeader>
      
      <CardContent className="space-y-6">
        {/* 定价说明 */}
        <div className="bg-muted/50 p-4 rounded-lg">
          <div className="flex items-center justify-between text-sm">
            <span>定价规则</span>
            <Badge variant="secondary">100 Credits = ¥2</Badge>
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            即 ¥{CREDITS_UNIT_PRICE}/Credit
          </div>
        </div>
        
        {/* 输入区域 */}
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="credits-amount">Credits数量</Label>
            <div className="flex gap-2">
              <Input
                id="credits-amount"
                type="number"
                value={creditsAmount}
                onChange={(e) => handleCreditsChange(e.target.value)}
                min={MIN_CREDITS_PURCHASE}
                step="100"
                className={!isValid ? 'border-red-500' : ''}
                placeholder={`最少 ${MIN_CREDITS_PURCHASE} Credits`}
              />
              <div className="flex items-center px-3 bg-muted rounded-md">
                <span className="text-sm text-muted-foreground">Credits</span>
              </div>
            </div>
            {!isValid && (
              <p className="text-sm text-red-500">
                最少需要购买 {MIN_CREDITS_PURCHASE} Credits
              </p>
            )}
          </div>
          
          {/* 快捷金额按钮 */}
          <div className="space-y-2">
            <Label className="text-sm text-muted-foreground">快捷选择</Label>
            <div className="grid grid-cols-2 gap-2">
              {quickAmounts.map((option) => (
                <Button
                  key={option.credits}
                  variant="outline"
                  size="sm"
                  onClick={() => handleQuickAmount(option.credits)}
                  className="justify-between"
                >
                  <span>{option.credits.toLocaleString()} Credits</span>
                  <span className="text-muted-foreground">¥{option.amount}</span>
                </Button>
              ))}
            </div>
          </div>
        </div>
        
        {/* 金额显示 */}
        <div className="bg-primary/5 p-4 rounded-lg border">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-muted-foreground">购买数量</div>
              <div className="text-lg font-semibold">
                {creditsAmount.toLocaleString()} Credits
              </div>
            </div>
            <div className="text-right">
              <div className="text-sm text-muted-foreground">应付金额</div>
              <div className="text-2xl font-bold text-primary">
                ¥{calculatedAmount.toFixed(2)}
              </div>
            </div>
          </div>
        </div>
        
        {/* 购买按钮 */}
        <Button
          className="w-full"
          size="lg"
          onClick={handlePurchase}
          disabled={!isValid}
        >
          <CreditCard className="mr-2 h-4 w-4" />
          立即购买 ¥{calculatedAmount.toFixed(2)}
        </Button>
        
        {/* 有效期说明 */}
        <div className="text-xs text-muted-foreground text-center">
          量包有效期为30天，购买后立即生效
        </div>
      </CardContent>
    </Card>
  )
}
