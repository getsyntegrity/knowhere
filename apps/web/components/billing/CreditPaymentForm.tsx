"use client"

import { useState } from 'react'
import { useStripe, useElements, CardElement } from '@stripe/react-stripe-js'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Loader2, CreditCard, CheckCircle } from 'lucide-react'
import { useToast } from '@/hooks/useToast'
import { api } from '@/lib/api'

interface CreditPaymentFormProps {
  creditsAmount: number
  amount: number
  onSuccess?: () => void
  onCancel?: () => void
}

export function CreditPaymentForm({ 
  creditsAmount, 
  amount, 
  onSuccess, 
  onCancel 
}: CreditPaymentFormProps) {
  const stripe = useStripe()
  const elements = useElements()
  const [isProcessing, setIsProcessing] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  const toast = useToast()

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()

    if (!stripe || !elements) {
      return
    }

    setIsProcessing(true)

    try {
      // 创建支付意图
      const response = await api.buyCredits(creditsAmount)
      
      if (!response.client_secret) {
        throw new Error('创建支付失败')
      }

      // 确认支付
      const { error, paymentIntent } = await stripe.confirmCardPayment(
        response.client_secret,
        {
          payment_method: {
            card: elements.getElement(CardElement)!,
            billing_details: {
              name: 'Credits购买',
            },
          },
        }
      )

      if (error) {
        console.error('Payment failed:', error)
        toast.error(`支付失败: ${error.message}`)
      } else if (paymentIntent.status === 'succeeded') {
        setIsSuccess(true)
        toast.success(`成功购买 ${creditsAmount} Credits!`)
        onSuccess?.()
      }
    } catch (error) {
      console.error('Payment error:', error)
      toast.error('支付处理失败，请稍后重试')
    } finally {
      setIsProcessing(false)
    }
  }

  if (isSuccess) {
    return (
      <Card>
        <CardContent className="pt-6">
          <div className="text-center space-y-4">
            <CheckCircle className="h-16 w-16 text-green-500 mx-auto" />
            <div>
              <h3 className="text-lg font-semibold">支付成功!</h3>
              <p className="text-muted-foreground">
                您已成功购买 {creditsAmount.toLocaleString()} Credits
              </p>
            </div>
            <Button onClick={onSuccess} className="w-full">
              完成
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CreditCard className="h-5 w-5" />
          支付信息
        </CardTitle>
        <CardDescription>
          购买 {creditsAmount.toLocaleString()} Credits，应付金额 ¥{amount.toFixed(2)}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="p-4 border rounded-lg">
            <CardElement
              options={{
                style: {
                  base: {
                    fontSize: '16px',
                    color: '#424770',
                    '::placeholder': {
                      color: '#aab7c4',
                    },
                  },
                },
              }}
            />
          </div>
          
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={onCancel}
              className="flex-1"
              disabled={isProcessing}
            >
              取消
            </Button>
            <Button
              type="submit"
              disabled={!stripe || isProcessing}
              className="flex-1"
            >
              {isProcessing ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  处理中...
                </>
              ) : (
                `支付 ¥${amount.toFixed(2)}`
              )}
            </Button>
          </div>
        </form>
        
        <div className="mt-4 p-3 bg-muted/50 rounded-lg">
          <p className="text-xs text-muted-foreground text-center">
            测试卡号: 4242 4242 4242 4242 | 有效期: 12/34 | CVC: 123
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
