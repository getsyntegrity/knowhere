"use client"

import { useEffect, useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { api } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { 
  CreditCard, 
  Key, 
  Activity, 
  TrendingUp,
  Plus,
  ExternalLink,
  Clock,
  CheckCircle,
  RefreshCw,
  AlertCircle
} from 'lucide-react'
import Link from 'next/link'
import { formatCredits, formatDate } from '@/lib/format'

interface DashboardStats {
  creditsBalance: number
  creditsLimit: number
  usagePercentage: number
  totalApiKeys: number
  activeApiKeys: number
  totalRequests: number
  totalKBJobs: number
  completedKBJobs: number
  runningKBJobs: number
  failedKBJobs: number
  recentActivity: Array<{
    id: string
    type: string
    description: string
    timestamp: string
    status?: string
  }>
}

export default function DashboardPage() {
  const { user } = useAuth()
  const { success, error, warning, info, loading } = useToast()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  useEffect(() => {
    if (user) {
      loadDashboardData()
    }
  }, [user])

  const loadDashboardData = async (isRefresh = false) => {
    try {
      if (isRefresh) {
        setIsRefreshing(true)
      } else {
        setIsLoading(true)
      }
      
      // 并行加载数据，使用 Promise.allSettled 来处理部分失败的情况
      const [
        creditsResult,
        apiKeysResult,
        usageResult,
        jobsResult,
        directoriesResult
      ] = await Promise.allSettled([
        api.getCreditsBalance(),
        api.listApiKeys(),
        api.getUsageStats('month'),
        api.listJobs({ page: 1, page_size: 100 }), // 使用新的统一Jobs API
        api.getDirectories() // 获取知识库目录数量
      ])

      // 处理各个API调用的结果
      const creditsData = creditsResult.status === 'fulfilled' ? creditsResult.value : null
      const apiKeysData = apiKeysResult.status === 'fulfilled' ? apiKeysResult.value : null
      const usageData = usageResult.status === 'fulfilled' ? usageResult.value : null
      const jobsData = jobsResult.status === 'fulfilled' ? jobsResult.value : null
      const directoriesData = directoriesResult.status === 'fulfilled' ? directoriesResult.value : null

      // 计算统计数据 - 使用新的统一Jobs API
      const allJobs = jobsData?.jobs || []
      const completedJobs = allJobs.filter((job: any) => job.status === 'done').length
      const runningJobs = allJobs.filter((job: any) => ['pending', 'converting', 'running'].includes(job.status)).length
      const failedJobs = allJobs.filter((job: any) => job.status === 'failed').length
      
      // 所有任务都按统一任务处理
      const completedKBJobs = completedJobs
      const runningKBJobs = runningJobs
      const failedKBJobs = failedJobs
      const totalKBJobs = jobsData?.total || 0

      // 构建最近活动数据
      const recentActivity: Array<{
        id: string
        type: string
        description: string
        timestamp: string
        status?: string
      }> = []
      
      // 添加最近的任务（使用新的统一Jobs API）
      if (allJobs && allJobs.length > 0) {
        const recentJobs = allJobs
          .sort((a: any, b: any) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
          .slice(0, 5) // 显示最近5个任务
        
        recentJobs.forEach((job: any) => {
          const getStatusText = (status: string) => {
            switch (status) {
              case 'done': return '已完成'
              case 'failed': return '失败'
              case 'waiting_for_upload': return '等待上传'
              case 'pending': return '排队中'
              case 'converting': return '转换中'
              case 'running': return '处理中'
              default: return '进行中'
            }
          }
          
          recentActivity.push({
            id: `job_${job.job_id}`,
            type: 'job',
            description: `任务 ${getStatusText(job.status)}`,
            timestamp: job.created_at,
            status: job.status
          })
        })
      }

      // 按时间排序最近活动
      recentActivity.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())

      setStats({
        creditsBalance: creditsData?.credits_balance || 0,
        creditsLimit: creditsData?.credits_limit || 100,
        usagePercentage: creditsData?.usage_percentage || 0,
        totalApiKeys: apiKeysData?.api_keys?.length || 0,
        activeApiKeys: apiKeysData?.api_keys?.filter((key: any) => key.is_active).length || 0,
        totalRequests: usageData?.api_calls_count || 0,
        totalKBJobs: totalKBJobs,
        completedKBJobs: completedKBJobs,
        runningKBJobs: runningKBJobs,
        failedKBJobs: failedKBJobs,
        recentActivity: recentActivity.slice(0, 6) // 只显示最近6个活动
      })

      // 更新最后更新时间
      setLastUpdated(new Date())
      
      // 显示成功消息
      if (isRefresh) {
        success('数据已刷新')
      } else {
        success('数据加载成功')
      }
    } catch (e) {
      console.error('Failed to load dashboard data:', e)
      error('加载数据失败，请检查网络连接')
    } finally {
      if (isRefresh) {
        setIsRefreshing(false)
      } else {
        setIsLoading(false)
      }
    }
  }

  const handleRefresh = () => {
    loadDashboardData(true)
  }

  if (!user) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">请先登录</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">无法加载仪表板数据</p>
        <Button onClick={() => loadDashboardData()} className="mt-4">
          重试
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 欢迎信息 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            欢迎回来，{user?.username}！
          </h1>
          <p className="text-muted-foreground">
            这是您的 Knowhere 账户概览
            {lastUpdated && (
              <span className="ml-2 text-xs">
                最后更新: {formatDate(lastUpdated.toISOString(), 'relative')}
              </span>
            )}
          </p>
        </div>
        <Button
          onClick={() => handleRefresh()}
          disabled={isRefreshing}
          variant="outline"
          size="sm"
          className="flex items-center gap-2"
        >
          <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          刷新
        </Button>
      </div>

      {/* 统计卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {/* Credits余额 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Credits余额</CardTitle>
            <CreditCard className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatCredits(stats.creditsBalance)}
            </div>
            <p className="text-xs text-muted-foreground">
              限制: {formatCredits(stats.creditsLimit)}
            </p>
            <div className="mt-2">
              <div className="w-full bg-muted rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full transition-all"
                  style={{ width: `${Math.min(stats.usagePercentage, 100)}%` }}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* API Keys */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">API Keys</CardTitle>
            <Key className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.activeApiKeys}</div>
            <p className="text-xs text-muted-foreground">
              共 {stats.totalApiKeys} 个
            </p>
          </CardContent>
        </Card>

        {/* 本月请求 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">本月请求</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{(stats.totalRequests || 0).toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              <TrendingUp className="inline h-3 w-3 mr-1" />
              +12% 较上月
            </p>
          </CardContent>
        </Card>

        {/* 使用率 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">使用率</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.usagePercentage.toFixed(1)}%</div>
            <p className="text-xs text-muted-foreground">
              Credits使用情况
            </p>
          </CardContent>
        </Card>

        {/* 任务状态 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">任务状态</CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.completedKBJobs}</div>
            <p className="text-xs text-muted-foreground">
              已完成 / 共 {stats.totalKBJobs} 个
            </p>
            <div className="mt-2 space-y-1">
              {stats.runningKBJobs > 0 && (
                <div className="flex items-center text-xs text-blue-600">
                  <Clock className="h-3 w-3 mr-1" />
                  进行中: {stats.runningKBJobs}
                </div>
              )}
              {stats.failedKBJobs > 0 && (
                <div className="flex items-center text-xs text-red-600">
                  <div className="h-3 w-3 mr-1 rounded-full bg-red-600" />
                  失败: {stats.failedKBJobs}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 快速操作 */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>任务管理</CardTitle>
            <CardDescription>
              创建和管理您的处理任务
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button asChild className="w-full justify-start">
              <Link href="/jobs">
                <Clock className="mr-2 h-4 w-4" />
                查看任务
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full justify-start">
              <Link href="/jobs">
                <Plus className="mr-2 h-4 w-4" />
                创建任务
              </Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>API 管理</CardTitle>
            <CardDescription>
              管理您的API Keys和账户设置
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button asChild className="w-full justify-start">
              <Link href="/api-keys">
                <Plus className="mr-2 h-4 w-4" />
                创建API Key
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full justify-start">
              <Link href="/billing">
                <CreditCard className="mr-2 h-4 w-4" />
                购买Credits
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full justify-start">
              <Link href="/settings">
                <ExternalLink className="mr-2 h-4 w-4" />
                账户设置
              </Link>
            </Button>
          </CardContent>
        </Card>

        {/* 最近活动 */}
        <Card>
          <CardHeader>
            <CardTitle>最近活动</CardTitle>
            <CardDescription>
              您的账户最新动态
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {stats.recentActivity.length > 0 ? (
                stats.recentActivity.map((activity) => {
                const getActivityIcon = (type: string, status?: string) => {
                  switch (type) {
                    case 'job':
                      if (status === 'done') return <CheckCircle className="h-4 w-4 text-green-500" />
                      if (status === 'failed') return <div className="h-4 w-4 rounded-full bg-red-500" />
                      return <Clock className="h-4 w-4 text-blue-500" />
                    case 'api_key':
                      return <Key className="h-4 w-4 text-purple-500" />
                    case 'billing':
                      return <CreditCard className="h-4 w-4 text-orange-500" />
                    default:
                      return <div className="h-2 w-2 rounded-full bg-primary" />
                  }
                }

                return (
                  <div key={activity.id} className="flex items-center space-x-3">
                    {getActivityIcon(activity.type, activity.status)}
                    <div className="flex-1 space-y-1">
                      <p className="text-sm font-medium">{activity.description}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatDate(activity.timestamp, 'relative')}
                      </p>
                    </div>
                  </div>
                )
                })
              ) : (
                <div className="text-center py-6">
                  <AlertCircle className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">暂无最近活动</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    开始使用知识库或创建任务来查看活动记录
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
