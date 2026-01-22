"use client"

import { useEffect, useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { api, type CreditsBalance, type UsageStats, type Transaction, type Subscription, type SubscriptionPlan, type CreditsPackage } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { EmptyState } from '@/components/common/EmptyState'
import { SubscriptionCard } from '@/components/billing/SubscriptionCard'
import { CreditPackageCard } from '@/components/billing/CreditPackageCard'
import { 
  CreditCard, 
  TrendingUp, 
  History, 
  Activity,
  Calendar,
  Download,
  Crown,
  Star
} from 'lucide-react'
import { formatCredits, formatCurrency, formatDate } from '@/lib/format'

// 默认免费套餐（如果数据库中没有配置）
const defaultFreePlan: SubscriptionPlan = {
    id: 'free',
  plan_id: 'free',
    name: 'Free',
    price: 0,
    period: 'month',
    credits: 100,
    features: ['基础API访问', '100 Credits/月', '标准支持'],
    popular: false
}

export default function BillingPage() {
  const { user } = useAuth()
  const toast = useToast()
  const [creditsBalance, setCreditsBalance] = useState<CreditsBalance | null>(null)
  const [usageStats, setUsageStats] = useState<UsageStats | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [currentSubscription, setCurrentSubscription] = useState<Subscription | null>(null)
  const [subscriptionPlans, setSubscriptionPlans] = useState<SubscriptionPlan[]>([defaultFreePlan])
  const [creditsPackages, setCreditsPackages] = useState<CreditsPackage[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [selectedPeriod, setSelectedPeriod] = useState('month')

  useEffect(() => {
    loadBillingData()
    
    // 处理支付成功/取消后的URL参数
    const urlParams = new URLSearchParams(window.location.search)
    const success = urlParams.get('success')
    const canceled = urlParams.get('canceled')
    const plan = urlParams.get('plan')
    const type = urlParams.get('type')
    
    if (success === 'true') {
      if (type === 'credits_package') {
        toast.success('Credits包购买成功！')
      } else if (plan) {
        toast.success(`订阅 ${plan} 成功！`)
      } else {
        toast.success('支付成功！')
      }
      // 清除URL参数
      window.history.replaceState({}, '', '/billing')
      // 重新加载数据
      loadBillingData()
    } else if (canceled === 'true') {
      toast.info('支付已取消')
      // 清除URL参数
      window.history.replaceState({}, '', '/billing')
    }
  }, [selectedPeriod])

  const loadBillingData = async () => {
    try {
      setIsLoading(true)
      
      const [creditsResponse, usageResponse, transactionsResponse, subscriptionResponse, priceConfigsResponse] = await Promise.allSettled([
        api.getCreditsBalance(),
        api.getUsageStats(selectedPeriod),
        api.getTransactionHistory(50, 0),
        api.getCurrentSubscription(),
        api.getPriceConfigs()
      ])

      // 处理各个API调用的结果
      const creditsData = creditsResponse.status === 'fulfilled' ? creditsResponse.value : null
      const usageData = usageResponse.status === 'fulfilled' ? usageResponse.value : null
      const transactionsData = transactionsResponse.status === 'fulfilled' ? transactionsResponse.value : null
      const subscriptionData = subscriptionResponse.status === 'fulfilled' ? subscriptionResponse.value : null
      const priceConfigsData = priceConfigsResponse.status === 'fulfilled' ? priceConfigsResponse.value : null

      // 记录错误
      if (creditsResponse.status === 'rejected') {
        console.error('获取Credits余额失败:', creditsResponse.reason)
      }
      if (usageResponse.status === 'rejected') {
        console.error('获取使用统计失败:', usageResponse.reason)
      }
      if (transactionsResponse.status === 'rejected') {
        console.error('获取交易历史失败:', transactionsResponse.reason)
      }
      if (subscriptionResponse.status === 'rejected') {
        console.warn('获取订阅信息失败（可能用户没有订阅）:', subscriptionResponse.reason)
      }
      if (priceConfigsResponse.status === 'rejected') {
        console.error('获取价格配置失败:', priceConfigsResponse.reason)
        toast.error('获取价格配置失败，请检查网络连接或联系管理员')
      }

      setCreditsBalance(creditsData)
      setUsageStats(usageData)
      setTransactions(transactionsData?.transactions || [])
      setCurrentSubscription(subscriptionData)
      
      // 处理价格配置
      if (priceConfigsData) {
        console.log('价格配置响应（原始数据）:', priceConfigsData)
        console.log('订阅计划数量:', priceConfigsData.subscriptions?.length || 0)
        console.log('Credits包数量:', priceConfigsData.credits_packages?.length || 0)
        
        // 验证数据结构
        if (!priceConfigsData.subscriptions && !priceConfigsData.credits_packages) {
          console.error('价格配置数据格式错误:', priceConfigsData)
          toast.error('价格配置数据格式错误')
          setSubscriptionPlans([defaultFreePlan])
          setCreditsPackages([])
          return
        }
        
        // 转换订阅计划格式，添加默认值
        const plans = (priceConfigsData.subscriptions || []).map(plan => {
          console.log('处理订阅计划:', plan.plan_id, 'amount_cents:', plan.amount_cents, 'metadata:', plan.metadata)
          
          // 处理价格：后端返回的是 amount_cents（单位：分），需要除以100转换为元
          let price = 0
          
          // 优先检查 amount_cents（数据库字段）
          if (plan.amount_cents != null && plan.amount_cents !== undefined) {
            if (plan.amount_cents > 0) {
              // amount_cents 大于 0 时，除以 100 转换为元
              price = plan.amount_cents / 100
              console.log(`计划 ${plan.plan_id}: amount_cents=${plan.amount_cents}, 转换为价格=${price}`)
            } else {
              // amount_cents 为 0 时，显示为免费
              price = 0
              console.log(`计划 ${plan.plan_id}: amount_cents=0, 显示为免费`)
            }
          } else if (plan.metadata?.price && typeof plan.metadata.price === 'number' && plan.metadata.price > 0) {
            // 如果 metadata 中有价格（已经是元），直接使用
            price = plan.metadata.price
            console.log(`计划 ${plan.plan_id}: 从metadata获取价格=${price}`)
          } else {
            // amount_cents 为 null 或 undefined，且 metadata 中没有价格
            console.warn(`计划 ${plan.plan_id}: amount_cents为null/undefined，且metadata中没有价格，显示为免费`)
            price = 0
          }
          
          // 处理 Credits：优先使用 metadata 中的 credits_limit，否则使用默认值
          let credits = 0
          if (plan.metadata?.credits_limit) {
            credits = plan.metadata.credits_limit
          } else if (plan.credits) {
            credits = plan.credits
          } else {
            // 根据 plan_id 设置默认值
            if (plan.plan_id === 'plus') credits = 1000
            else if (plan.plan_id === 'pro') credits = 10000
            else credits = 100
          }
          
          return {
            ...plan,
            id: plan.plan_id,
            price: typeof price === 'number' ? price : parseFloat(price as any) || 0,
            period: plan.period || 'month',
            credits: credits,
            features: plan.features || [],
          }
        })
        
        console.log('处理后的订阅计划:', plans.map(p => ({ 
          id: p.id, 
          name: p.name, 
          price: p.price, 
          amount_cents: p.amount_cents,
          credits: p.credits 
        })))
        
        // 如果没有订阅计划，使用默认免费套餐
        if (plans.length === 0) {
          setSubscriptionPlans([defaultFreePlan])
        } else {
          // 添加免费套餐到开头
          setSubscriptionPlans([defaultFreePlan, ...plans])
        }
        
        // 设置Credits包
        if (priceConfigsData.credits_packages && priceConfigsData.credits_packages.length > 0) {
          console.log('Credits包数据:', priceConfigsData.credits_packages)
          setCreditsPackages(priceConfigsData.credits_packages)
        } else {
          console.log('没有Credits包数据')
          setCreditsPackages([])
        }
      }
    } catch (error) {
      console.error('Failed to load billing data:', error)
      toast.error('加载计费数据失败')
      // 设置默认值，避免undefined错误
      setCreditsBalance(null)
      setUsageStats(null)
      setTransactions([])
      setCurrentSubscription(null)
      setSubscriptionPlans([defaultFreePlan])
      setCreditsPackages([])
    } finally {
      setIsLoading(false)
    }
  }

  const handleSubscriptionChange = () => {
    // 订阅状态改变后重新加载数据
    loadBillingData()
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 页面标题 */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">计费</h1>
        <p className="text-muted-foreground">
          管理您的订阅和Credits
        </p>
      </div>

      {/* 当前状态概览 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {/* 当前订阅 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">当前订阅</CardTitle>
            <Crown className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {currentSubscription ? subscriptionPlans.find(p => p.id === currentSubscription.plan_type || p.plan_id === currentSubscription.plan_type)?.name || 'Free' : 'Free'}
            </div>
            <p className="text-xs text-muted-foreground">
              {currentSubscription?.status === 'active' ? '已激活' : '未激活'}
            </p>
          </CardContent>
        </Card>

        {/* Credits余额 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Credits余额</CardTitle>
            <CreditCard className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {creditsBalance ? formatCredits(creditsBalance.credits_balance) : '0'}
            </div>
            <p className="text-xs text-muted-foreground">
              Credits
            </p>
          </CardContent>
        </Card>

        {/* 月度限制 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">月度限制</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {creditsBalance ? formatCredits(creditsBalance.credits_limit) : '100'}
            </div>
            <p className="text-xs text-muted-foreground">
              Credits/月
            </p>
          </CardContent>
        </Card>

        {/* 使用率 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">使用率</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {creditsBalance ? creditsBalance.usage_percentage.toFixed(1) : '0'}%
            </div>
            <div className="mt-2">
              <div className="w-full bg-muted rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full transition-all"
                  style={{ width: `${Math.min(creditsBalance?.usage_percentage || 0, 100)}%` }}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 主要内容 */}
      <Tabs defaultValue="plans" className="space-y-4">
        <TabsList>
          <TabsTrigger value="plans">订阅套餐</TabsTrigger>
          <TabsTrigger value="credits">Credits量包</TabsTrigger>
          <TabsTrigger value="usage">使用情况</TabsTrigger>
          <TabsTrigger value="transactions">交易记录</TabsTrigger>
        </TabsList>

        {/* 订阅套餐标签页 */}
        <TabsContent value="plans" className="space-y-6">
          <div>
            <h2 className="text-2xl font-bold mb-2">选择您的订阅套餐</h2>
            <p className="text-muted-foreground">
              订阅套餐提供每月固定的Credits额度，适合长期使用
            </p>
          </div>
          
          <div className="grid gap-6 md:grid-cols-3">
            {subscriptionPlans.map((plan) => (
              <SubscriptionCard
                key={plan.id}
                plan={plan}
                currentSubscription={currentSubscription}
                onSubscriptionChange={handleSubscriptionChange}
              />
            ))}
          </div>
        </TabsContent>

        {/* Credits量包标签页 */}
        <TabsContent value="credits" className="space-y-6">
          <div>
            <h2 className="text-2xl font-bold mb-2">购买Credits量包</h2>
            <p className="text-muted-foreground">
              一次性购买Credits，30天内有效。先消耗订阅赠送的Credits，再消耗量包Credits
            </p>
          </div>
          
          {creditsPackages.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {creditsPackages.map((pkg) => {
                // 后端返回的是 amount_cents（单位：分），需要除以100转换为元
                const priceInYuan = pkg.amount_cents != null && pkg.amount_cents !== undefined
                  ? pkg.amount_cents / 100
                  : 0
                const price = priceInYuan.toFixed(2)
                const credits = pkg.credits_amount != null && pkg.credits_amount !== undefined
                  ? pkg.credits_amount
                  : 0
                
                return (
                  <Card key={pkg.id || pkg.price_id} className="relative">
                    <CardHeader>
                      <CardTitle className="text-xl">{pkg.name || `${credits} Credits`}</CardTitle>
                      <CardDescription>{pkg.description || `${credits} Credits`}</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="text-center">
                        <div className="text-3xl font-bold text-primary">
                          {credits.toLocaleString()}
                        </div>
                        <div className="text-sm text-muted-foreground">Credits</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold">
                          ¥{price}
                        </div>
                      </div>
                      <Button
                        className="w-full"
                        onClick={async () => {
                          try {
                            const response = await api.buyCreditsPackage(pkg.price_id)
                            if (response.checkout_url) {
                              window.location.href = response.checkout_url
                            }
                          } catch (error) {
                            console.error('购买失败:', error)
                            toast.error('购买失败，请稍后重试')
                          }
                        }}
                      >
                        立即购买
                      </Button>
                    </CardContent>
                  </Card>
                )
              })}
          </div>
          ) : (
            <Card>
              <CardContent className="py-8">
                <p className="text-center text-muted-foreground">暂无可用的Credits包</p>
                <p className="text-center text-xs text-muted-foreground mt-2">
                  请先在数据库中配置价格信息
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* 使用情况标签页 */}
        <TabsContent value="usage" className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>使用统计</CardTitle>
                  <CardDescription>
                    您的API使用情况
                  </CardDescription>
                </div>
                <Select value={selectedPeriod} onValueChange={setSelectedPeriod}>
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="week">最近一周</SelectItem>
                    <SelectItem value="month">最近一月</SelectItem>
                    <SelectItem value="year">最近一年</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent>
              {usageStats ? (
                <div className="space-y-4">
                  <div className="grid gap-4 md:grid-cols-3">
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">总请求数</span>
                      <span className="font-medium">{(usageStats.api_calls_count || 0).toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">已使用Credits</span>
                      <span className="font-medium">{formatCredits(usageStats.total_credits_used || 0)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">成功率</span>
                      <span className="font-medium">{(usageStats.success_rate || 0).toFixed(1)}%</span>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">暂无使用数据</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>


        {/* 交易记录标签页 */}
        <TabsContent value="transactions" className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>交易记录</CardTitle>
                  <CardDescription>
                    查看您的所有交易记录
                  </CardDescription>
                </div>
                <Button variant="outline" size="sm">
                  <Download className="mr-2 h-4 w-4" />
                  导出
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {transactions.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>类型</TableHead>
                      <TableHead>描述</TableHead>
                      <TableHead>金额</TableHead>
                      <TableHead>时间</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {transactions.map((transaction) => (
                      <TableRow key={transaction.id}>
                        <TableCell>
                          <Badge variant={transaction.type === 'credit' ? 'default' : 'secondary'}>
                            {transaction.type === 'credit' ? '充值' : '消费'}
                          </Badge>
                        </TableCell>
                        <TableCell>{transaction.description}</TableCell>
                        <TableCell className={transaction.type === 'credit' ? 'text-green-600' : 'text-red-600'}>
                          {transaction.type === 'credit' ? '+' : '-'}{formatCredits(transaction.credits_amount)}
                        </TableCell>
                        <TableCell>{formatDate(transaction.created_at, 'long')}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <EmptyState
                  icon={<History className="h-12 w-12 text-muted-foreground" />}
                  title="暂无交易记录"
                  description="您的交易记录将显示在这里"
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

    </div>
  )
}
