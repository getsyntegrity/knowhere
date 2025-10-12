"use client"

import { useEffect, useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { api, type CreditsBalance, type UsageStats, type Transaction, type Subscription, type SubscriptionPlan } from '@/lib/api'
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

// 订阅套餐定义
const subscriptionPlans: SubscriptionPlan[] = [
  {
    id: 'free',
    name: 'Free',
    price: 0,
    period: 'month',
    credits: 100,
    features: ['基础API访问', '100 Credits/月', '标准支持'],
    popular: false
  },
  {
    id: 'plus',
    name: 'Plus',
    price: 29,
    period: 'month',
    credits: 1000,
    features: ['完整API访问', '1,000 Credits/月', '优先支持', '高级功能'],
    popular: true
  },
  {
    id: 'pro',
    name: 'Pro',
    price: 99,
    period: 'month',
    credits: 10000,
    features: ['无限API访问', '10,000 Credits/月', '专属支持', '所有高级功能', '自定义集成'],
    popular: false
  }
]

export default function BillingPage() {
  const { user } = useAuth()
  const toast = useToast()
  const [creditsBalance, setCreditsBalance] = useState<CreditsBalance | null>(null)
  const [usageStats, setUsageStats] = useState<UsageStats | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [currentSubscription, setCurrentSubscription] = useState<Subscription | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [selectedPeriod, setSelectedPeriod] = useState('month')

  useEffect(() => {
    loadBillingData()
  }, [selectedPeriod])

  const loadBillingData = async () => {
    try {
      setIsLoading(true)
      
      const [creditsResponse, usageResponse, transactionsResponse, subscriptionResponse] = await Promise.all([
        api.getCreditsBalance(),
        api.getUsageStats(selectedPeriod),
        api.getTransactionHistory(50, 0),
        api.getCurrentSubscription().catch(() => null) // 订阅信息可能不存在
      ])

      setCreditsBalance(creditsResponse)
      setUsageStats(usageResponse)
      setTransactions(transactionsResponse?.transactions || [])
      setCurrentSubscription(subscriptionResponse)
    } catch (error) {
      console.error('Failed to load billing data:', error)
      toast.error('加载计费数据失败')
      // 设置默认值，避免undefined错误
      setCreditsBalance(null)
      setUsageStats(null)
      setTransactions([])
      setCurrentSubscription(null)
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
              {currentSubscription ? subscriptionPlans.find(p => p.id === currentSubscription.plan_type)?.name || 'Free' : 'Free'}
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
          
          <div className="max-w-2xl">
            <CreditPackageCard />
          </div>
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
                          {transaction.type === 'credit' ? '+' : '-'}{formatCredits(transaction.amount)}
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
