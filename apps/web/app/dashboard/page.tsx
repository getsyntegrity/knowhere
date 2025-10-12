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
  BookOpen,
  Search,
  Clock,
  CheckCircle,
  FileText,
  ClipboardEdit,
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
  totalKnowledgeBases: number
  totalKBJobs: number
  completedKBJobs: number
  runningKBJobs: number
  failedKBJobs: number
  totalTableDocs: number
  totalTableFillJobs: number
  completedTableFillJobs: number
  runningTableFillJobs: number
  failedTableFillJobs: number
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
    loadDashboardData()
  }, [])

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
        kbJobsResult,
        tableFillJobsResult,
        directoriesResult
      ] = await Promise.allSettled([
        api.getCreditsBalance(),
        api.listApiKeys(),
        api.getUsageStats('month'),
        api.getKBJobs({ page: 1, limit: 100 }),
        api.listTableFillJobs(1, 100),
        api.getDirectories() // 获取知识库目录数量
      ])

      // 处理各个API调用的结果
      const creditsData = creditsResult.status === 'fulfilled' ? creditsResult.value : null
      const apiKeysData = apiKeysResult.status === 'fulfilled' ? apiKeysResult.value : null
      const usageData = usageResult.status === 'fulfilled' ? usageResult.value : null
      const kbJobsData = kbJobsResult.status === 'fulfilled' ? kbJobsResult.value : null
      const tableFillJobsData = tableFillJobsResult.status === 'fulfilled' ? tableFillJobsResult.value : null
      const directoriesData = directoriesResult.status === 'fulfilled' ? directoriesResult.value : null

      // 计算统计数据
      const completedJobs = kbJobsData?.jobs?.filter((job: any) => job.status === 'completed').length || 0
      const runningJobs = kbJobsData?.jobs?.filter((job: any) => job.status === 'running' || job.status === 'pending').length || 0
      const failedJobs = kbJobsData?.jobs?.filter((job: any) => job.status === 'failed').length || 0
      
      const completedTableFillJobs = tableFillJobsData?.jobs?.filter((job: any) => job.status === 'completed').length || 0
      const runningTableFillJobs = tableFillJobsData?.jobs?.filter((job: any) => job.status === 'running' || job.status === 'pending').length || 0
      const failedTableFillJobs = tableFillJobsData?.jobs?.filter((job: any) => job.status === 'failed').length || 0

      // 构建最近活动数据
      const recentActivity: Array<{
        id: string
        type: string
        description: string
        timestamp: string
        status?: string
      }> = []
      
      // 添加最近的知识库任务
      if (kbJobsData?.jobs && kbJobsData.jobs.length > 0) {
        const recentKBJobs = kbJobsData.jobs
          .sort((a: any, b: any) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
          .slice(0, 3)
        
        recentKBJobs.forEach((job: any) => {
          recentActivity.push({
            id: `kb_job_${job.job_id}`,
            type: 'kb_job',
            description: `知识库任务 ${job.status === 'completed' ? '已完成' : job.status === 'failed' ? '失败' : '进行中'}`,
            timestamp: job.created_at,
            status: job.status
          })
        })
      }

      // 添加最近的表格填充任务
      if (tableFillJobsData?.jobs && tableFillJobsData.jobs.length > 0) {
        const recentTableFillJobs = tableFillJobsData.jobs
          .sort((a: any, b: any) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
          .slice(0, 2)
        
        recentTableFillJobs.forEach((job: any) => {
          recentActivity.push({
            id: `table_fill_${job.job_id}`,
            type: 'table_fill',
            description: `表格填充任务 ${job.status === 'completed' ? '已完成' : job.status === 'failed' ? '失败' : '进行中'}`,
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
        totalKnowledgeBases: directoriesData?.length || 0,
        totalKBJobs: kbJobsData?.total || 0,
        completedKBJobs: completedJobs,
        runningKBJobs: runningJobs,
        failedKBJobs: failedJobs,
        totalTableDocs: 0, // 这个需要单独的API来获取
        totalTableFillJobs: tableFillJobsData?.total || 0,
        completedTableFillJobs: completedTableFillJobs,
        runningTableFillJobs: runningTableFillJobs,
        failedTableFillJobs: failedTableFillJobs,
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
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
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

        {/* 知识库数量 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">知识库</CardTitle>
            <BookOpen className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalKnowledgeBases}</div>
            <p className="text-xs text-muted-foreground">
              个知识库
            </p>
          </CardContent>
        </Card>

        {/* 知识库任务状态 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">知识库任务</CardTitle>
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

        {/* 表格文档数量 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">表格文档</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalTableDocs}</div>
            <p className="text-xs text-muted-foreground">
              个文档
            </p>
          </CardContent>
        </Card>

        {/* 表格填充任务状态 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">表格填充</CardTitle>
            <ClipboardEdit className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.completedTableFillJobs}</div>
            <p className="text-xs text-muted-foreground">
              已完成 / 共 {stats.totalTableFillJobs} 个
            </p>
            <div className="mt-2 space-y-1">
              {stats.runningTableFillJobs > 0 && (
                <div className="flex items-center text-xs text-blue-600">
                  <Clock className="h-3 w-3 mr-1" />
                  进行中: {stats.runningTableFillJobs}
                </div>
              )}
              {stats.failedTableFillJobs > 0 && (
                <div className="flex items-center text-xs text-red-600">
                  <div className="h-3 w-3 mr-1 rounded-full bg-red-600" />
                  失败: {stats.failedTableFillJobs}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 快速操作 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>知识库管理</CardTitle>
            <CardDescription>
              管理您的知识库内容和文档
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button asChild className="w-full justify-start">
              <Link href="/knowledge-base">
                <BookOpen className="mr-2 h-4 w-4" />
                管理知识库
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full justify-start">
              <Link href="/kb-search">
                <Search className="mr-2 h-4 w-4" />
                搜索知识库
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full justify-start">
              <Link href="/kb-jobs">
                <Clock className="mr-2 h-4 w-4" />
                查看任务
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

        <Card>
          <CardHeader>
            <CardTitle>表格填充管理</CardTitle>
            <CardDescription>
              管理您的表格文档和填充任务
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button asChild className="w-full justify-start">
              <Link href="/table-docs">
                <FileText className="mr-2 h-4 w-4" />
                管理表格文档
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full justify-start">
              <Link href="/table-fill-jobs">
                <ClipboardEdit className="mr-2 h-4 w-4" />
                查看填充任务
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full justify-start">
              <Link href="/table-docs">
                <Plus className="mr-2 h-4 w-4" />
                上传新文档
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
                    case 'knowledge_base':
                      return <BookOpen className="h-4 w-4 text-blue-500" />
                    case 'kb_job':
                      if (status === 'completed') return <CheckCircle className="h-4 w-4 text-green-500" />
                      if (status === 'failed') return <div className="h-4 w-4 rounded-full bg-red-500" />
                      return <Clock className="h-4 w-4 text-blue-500" />
                    case 'table_fill':
                      if (status === 'completed') return <CheckCircle className="h-4 w-4 text-green-500" />
                      if (status === 'failed') return <div className="h-4 w-4 rounded-full bg-red-500" />
                      return <ClipboardEdit className="h-4 w-4 text-blue-500" />
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
