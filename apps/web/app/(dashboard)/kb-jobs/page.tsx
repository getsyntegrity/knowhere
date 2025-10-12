"use client"

import { useState, useEffect } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { api } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { 
  Plus, 
  Search, 
  Upload, 
  FileText,
  RefreshCw,
  X,
  CheckCircle,
  XCircle,
  Clock,
  AlertCircle
} from 'lucide-react'
import { formatDate } from '@/lib/format'

interface KBJobResponse {
  job_id: string
  status: string
  current_state: string
  source_type: string
  file_path?: string
  s3_key?: string
  result_s3_key?: string
  webhook_url?: string
  webhook_enabled: boolean
  error_message?: string
  created_at: string
  updated_at: string
}

interface KBJobCreateRequest {
  source_type: 'url'
  file_url?: string
  webhook_url?: string
  metadata?: Record<string, any>
}

export default function KBJobsPage() {
  const { user } = useAuth()
  const toast = useToast()
  const [jobs, setJobs] = useState<KBJobResponse[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isCreatingJob, setIsCreatingJob] = useState(false)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')

  // 创建任务表单状态
  const [createJobForm, setCreateJobForm] = useState<KBJobCreateRequest>({
    source_type: 'file_upload',
    file_url: '',
    webhook_url: '',
    metadata: {
      doc_type: 'auto',
      kb_dir: '默认目录',
      smart_title_parse: true,
      summary_image: false,
      summary_table: true,
      summary_txt: true,
      add_frag_desc: ''
    }
  })

  // 文件上传状态
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)

  useEffect(() => {
    loadJobs()
  }, [])

  // 定期刷新任务状态 - 只在有运行中的任务时才启用定时器
  useEffect(() => {
    // 检查是否有运行中的任务
    const hasRunningJobs = jobs.some(job => job.status === 'running' || job.status === 'pending')
    
    if (!hasRunningJobs) {
      return // 没有运行中的任务，不启动定时器
    }

    const interval = setInterval(() => {
      loadJobs(false) // 自动刷新不显示加载状态
    }, 10000) // 增加到10秒刷新一次，减少请求频率

    return () => clearInterval(interval)
  }, [jobs]) // 依赖jobs数组，当任务状态变化时重新评估

  const loadJobs = async (showLoading = true) => {
    try {
      if (showLoading) {
        setIsLoading(true)
      } else {
        setIsRefreshing(true)
      }
      const response = await api.getKBJobs({ limit: 50 })
      setJobs(response?.jobs || [])
    } catch (error) {
      console.error('Failed to load jobs:', error)
      if (showLoading) {
        toast.error('加载任务列表失败')
      }
    } finally {
      if (showLoading) {
        setIsLoading(false)
      } else {
        setIsRefreshing(false)
      }
    }
  }

  // 手动刷新函数
  const handleManualRefresh = () => {
    loadJobs()
  }

  const handleCreateJob = async () => {
    try {
      setIsCreatingJob(true)
      
      if (createJobForm.source_type === 'file_upload') {
        if (!selectedFile) {
          toast.error('请选择要上传的文件')
          return
        }
        
        // 使用文件上传接口
        await api.uploadFileAndCreateKBJob(selectedFile, createJobForm.webhook_url, createJobForm.metadata)
      } else {
        // 使用URL接口
        await api.createKBJob({
          source_type: 'url',
          file_url: createJobForm.file_url,
          webhook_url: createJobForm.webhook_url,
          metadata: createJobForm.metadata
        })
      }
      
      toast.success('任务创建成功')
      setShowCreateDialog(false)
      setCreateJobForm({
        source_type: 'file_upload',
        file_url: '',
        webhook_url: '',
        metadata: {
          doc_type: 'auto',
          kb_dir: '默认目录',
          smart_title_parse: true,
          summary_image: false,
          summary_table: true,
          summary_txt: true,
          add_frag_desc: ''
        }
      })
      setSelectedFile(null)
      loadJobs()
    } catch (error) {
      console.error('Failed to create job:', error)
      toast.error('创建任务失败')
    } finally {
      setIsCreatingJob(false)
    }
  }

  const handleRetryJob = async (jobId: string) => {
    try {
      await api.retryKBJob(jobId)
      toast.success('任务重试成功')
      loadJobs()
    } catch (error) {
      console.error('Failed to retry job:', error)
      toast.error('重试任务失败')
    }
  }

  const handleCancelJob = async (jobId: string) => {
    try {
      await api.cancelKBJob(jobId)
      toast.success('任务已取消')
      loadJobs()
    } catch (error) {
      console.error('Failed to cancel job:', error)
      toast.error('取消任务失败')
    }
  }

  // 文件拖拽处理
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    
    const files = e.dataTransfer.files
    if (files.length > 0) {
      const file = files[0]
      // 检查文件类型
      const allowedTypes = ['.pdf', '.doc', '.docx', '.txt', '.md', '.xlsx', '.xls', '.csv']
      const fileExtension = '.' + file.name.split('.').pop()?.toLowerCase()
      
      if (allowedTypes.includes(fileExtension)) {
        setSelectedFile(file)
      } else {
        toast.error('不支持的文件格式，请选择 PDF, DOC, DOCX, TXT, MD, XLSX, XLS, CSV 格式的文件')
      }
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" />
      case 'running':
        return <Clock className="h-4 w-4 text-blue-500" />
      default:
        return <AlertCircle className="h-4 w-4 text-gray-500" />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800'
      case 'failed':
        return 'bg-red-100 text-red-800'
      case 'running':
        return 'bg-blue-100 text-blue-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const filteredJobs = jobs.filter(job => {
    const matchesSearch = job.job_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         job.file_path?.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         job.s3_key?.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesStatus = statusFilter === 'all' || job.status === statusFilter
    return matchesSearch && matchesStatus
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 页面标题和操作 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">知识库任务管理</h1>
          <p className="text-muted-foreground">
            管理您的知识库处理任务，监控任务状态和进度
          </p>
        </div>
        <Button onClick={() => setShowCreateDialog(true)}>
          <Plus className="mr-2 h-4 w-4" />
          创建任务
        </Button>
      </div>

      {/* 自动刷新指示器 */}
      {isRefreshing && (
        <div className="flex items-center justify-center py-2 px-4 bg-blue-50 border border-blue-200 rounded-md">
          <RefreshCw className="mr-2 h-4 w-4 animate-spin text-blue-600" />
          <span className="text-sm text-blue-600">正在自动刷新任务状态...</span>
        </div>
      )}

      {/* 搜索和筛选 */}
      <div className="flex items-center space-x-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
          <Input
            placeholder="搜索任务..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="状态筛选" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="pending">等待中</SelectItem>
            <SelectItem value="running">运行中</SelectItem>
            <SelectItem value="completed">已完成</SelectItem>
            <SelectItem value="failed">失败</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" onClick={handleManualRefresh} disabled={isLoading || isRefreshing}>
          <RefreshCw className={`mr-2 h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          {isRefreshing ? '刷新中...' : '刷新'}
        </Button>
      </div>

      {/* 任务列表 */}
      {filteredJobs.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-8">
            <Upload className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">暂无任务</h3>
            <p className="text-muted-foreground text-center mb-4">
              您还没有创建任何知识库处理任务
            </p>
            <Button onClick={() => setShowCreateDialog(true)}>
              <Plus className="mr-2 h-4 w-4" />
              创建第一个任务
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {filteredJobs.map((job) => (
            <Card key={job.job_id}>
              <CardContent className="p-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center space-x-3 mb-3">
                      {getStatusIcon(job.status)}
                      <h3 className="font-medium text-lg">{job.job_id}</h3>
                      <Badge className={getStatusColor(job.status)}>
                        {job.status}
                      </Badge>
                      <span className="text-sm text-muted-foreground">
                        {job.current_state}
                      </span>
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-muted-foreground">
                      <div>
                        <p><strong>源类型:</strong> {job.source_type}</p>
                        {job.file_path && <p><strong>文件路径:</strong> {job.file_path}</p>}
                        {job.s3_key && <p><strong>S3键:</strong> {job.s3_key}</p>}
                        {job.webhook_url && <p><strong>Webhook:</strong> {job.webhook_url}</p>}
                      </div>
                      <div>
                        <p><strong>创建时间:</strong> {formatDate(job.created_at)}</p>
                        <p><strong>更新时间:</strong> {formatDate(job.updated_at)}</p>
                        {job.error_message && (
                          <p className="text-red-600"><strong>错误:</strong> {job.error_message}</p>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center space-x-2 ml-4">
                    {job.status === 'failed' && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleRetryJob(job.job_id)}
                      >
                        <RefreshCw className="mr-1 h-3 w-3" />
                        重试
                      </Button>
                    )}
                    {job.status === 'running' && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleCancelJob(job.job_id)}
                      >
                        <X className="mr-1 h-3 w-3" />
                        取消
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* 创建任务对话框 */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>创建知识库处理任务</DialogTitle>
            <DialogDescription>
              创建异步任务来处理文档，支持URL和直接上传两种方式
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="source_type">源类型</Label>
              <Select
                value={createJobForm.source_type}
                onValueChange={(value: 'file_upload' | 'url') => 
                  setCreateJobForm({ ...createJobForm, source_type: value })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="file_upload">文件上传</SelectItem>
                  <SelectItem value="url">URL链接</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            {createJobForm.source_type === 'url' ? (
              <div>
                <Label htmlFor="file_url">文件URL</Label>
                <Input
                  id="file_url"
                  placeholder="https://example.com/document.pdf"
                  value={createJobForm.file_url}
                  onChange={(e) => setCreateJobForm({ ...createJobForm, file_url: e.target.value })}
                />
              </div>
            ) : (
              <div>
                <Label>选择文件</Label>
                <div 
                  className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer ${
                    isDragOver 
                      ? 'border-blue-400 bg-blue-50' 
                      : 'border-gray-300 hover:border-gray-400'
                  }`}
                  onClick={() => document.getElementById('file_upload')?.click()}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                >
                  <input
                    id="file_upload"
                    type="file"
                    accept=".pdf,.doc,.docx,.txt,.md,.xlsx,.xls,.csv"
                    onChange={(e) => {
                      const file = e.target.files?.[0] || null
                      if (file) {
                        // 检查文件类型
                        const allowedTypes = ['.pdf', '.doc', '.docx', '.txt', '.md', '.xlsx', '.xls', '.csv']
                        const fileExtension = '.' + file.name.split('.').pop()?.toLowerCase()
                        
                        if (allowedTypes.includes(fileExtension)) {
                          setSelectedFile(file)
                        } else {
                          toast.error('不支持的文件格式，请选择 PDF, DOC, DOCX, TXT, MD, XLSX, XLS, CSV 格式的文件')
                        }
                      }
                    }}
                    className="hidden"
                  />
                  
                  {selectedFile ? (
                    <div className="space-y-2">
                      <FileText className="h-12 w-12 text-green-500 mx-auto" />
                      <div className="text-sm font-medium text-gray-900">
                        {selectedFile.name}
                      </div>
                      <div className="text-xs text-gray-500">
                        {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelectedFile(null)
                          const input = document.getElementById('file_upload') as HTMLInputElement
                          if (input) input.value = ''
                        }}
                      >
                        重新选择
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <Upload className="h-12 w-12 text-gray-400 mx-auto" />
                      <div className="text-sm font-medium text-gray-900">
                        点击选择文件或拖拽文件到此处
                      </div>
                      <div className="text-xs text-gray-500">
                        支持 PDF, DOC, DOCX, TXT, MD, XLSX, XLS, CSV 格式
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div>
              <Label htmlFor="webhook_url">Webhook URL (可选)</Label>
              <Input
                id="webhook_url"
                placeholder="https://your-webhook.com/callback"
                value={createJobForm.webhook_url}
                onChange={(e) => setCreateJobForm({ ...createJobForm, webhook_url: e.target.value })}
              />
            </div>

            <div className="space-y-4 border-t pt-4">
              <h4 className="font-medium">处理配置</h4>
              
              <div>
                <Label htmlFor="kb_dir">知识库目录</Label>
                <Input
                  id="kb_dir"
                  placeholder="默认目录"
                  value={createJobForm.metadata?.kb_dir || ''}
                  onChange={(e) => setCreateJobForm({
                    ...createJobForm,
                    metadata: { ...createJobForm.metadata, kb_dir: e.target.value }
                  })}
                />
              </div>

              <div>
                <Label htmlFor="doc_type">文档类型</Label>
                <Select
                  value={createJobForm.metadata?.doc_type || 'auto'}
                  onValueChange={(value) => setCreateJobForm({
                    ...createJobForm,
                    metadata: { ...createJobForm.metadata, doc_type: value }
                  })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">自动检测</SelectItem>
                    <SelectItem value="pdf">PDF</SelectItem>
                    <SelectItem value="docx">Word文档</SelectItem>
                    <SelectItem value="xlsx">Excel表格</SelectItem>
                    <SelectItem value="pptx">PowerPoint</SelectItem>
                    <SelectItem value="txt">文本文件</SelectItem>
                    <SelectItem value="md">Markdown</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label htmlFor="smart_title_parse">智能标题解析</Label>
                  <Switch
                    id="smart_title_parse"
                    checked={createJobForm.metadata?.smart_title_parse || false}
                    onCheckedChange={(checked) => setCreateJobForm({
                      ...createJobForm,
                      metadata: { ...createJobForm.metadata, smart_title_parse: checked }
                    })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="summary_image">图像摘要</Label>
                  <Switch
                    id="summary_image"
                    checked={createJobForm.metadata?.summary_image || false}
                    onCheckedChange={(checked) => setCreateJobForm({
                      ...createJobForm,
                      metadata: { ...createJobForm.metadata, summary_image: checked }
                    })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="summary_table">表格摘要</Label>
                  <Switch
                    id="summary_table"
                    checked={createJobForm.metadata?.summary_table || false}
                    onCheckedChange={(checked) => setCreateJobForm({
                      ...createJobForm,
                      metadata: { ...createJobForm.metadata, summary_table: checked }
                    })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="summary_txt">文本摘要</Label>
                  <Switch
                    id="summary_txt"
                    checked={createJobForm.metadata?.summary_txt || false}
                    onCheckedChange={(checked) => setCreateJobForm({
                      ...createJobForm,
                      metadata: { ...createJobForm.metadata, summary_txt: checked }
                    })}
                  />
                </div>
              </div>

              <div>
                <Label htmlFor="add_frag_desc">额外描述</Label>
                <Textarea
                  id="add_frag_desc"
                  placeholder="针对文档的人工描述..."
                  value={createJobForm.metadata?.add_frag_desc || ''}
                  onChange={(e) => setCreateJobForm({
                    ...createJobForm,
                    metadata: { ...createJobForm.metadata, add_frag_desc: e.target.value }
                  })}
                />
              </div>
            </div>

            <div className="flex justify-end space-x-2">
              <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
                取消
              </Button>
              <Button onClick={handleCreateJob} disabled={isCreatingJob}>
                {isCreatingJob ? (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                    创建中...
                  </>
                ) : (
                  '创建任务'
                )}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}