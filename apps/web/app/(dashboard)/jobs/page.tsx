"use client"

import { useState, useEffect } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { api, JobResponse, JobStatus, JobCreate, ParsingParams } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Progress } from '@/components/ui/progress'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { EmptyState } from '@/components/common/EmptyState'
import FileUploadFlow from '@/components/jobs/FileUploadFlow'
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
  AlertCircle,
  Download,
  Eye,
  Loader2
} from 'lucide-react'
import { formatDate } from '@/lib/format'

export default function JobsPage() {
  const { user } = useAuth()
  const toast = useToast()
  const [jobs, setJobs] = useState<JobResponse[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [selectedJob, setSelectedJob] = useState<JobResponse | null>(null)
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null)
  const [directories, setDirectories] = useState<Array<{id: string, title: string}>>([])

  // 创建任务表单状态
  const [createForm, setCreateForm] = useState<{
    source_type: 'file' | 'url'
    source_url: string
    data_id: string
    parsing_params: ParsingParams
    webhook: {
      url: string
      secret: string
    }
    result_mode: 'auto' | 'inline' | 'url'
  }>({
    source_type: 'file',
    source_url: '',
    data_id: '',
    parsing_params: {
      kb_dir: '',
      doc_type: 'auto',
      smart_title_parse: true,
      summary_image: false,
      summary_table: true,
      summary_txt: true,
      add_frag_desc: ''
    },
    webhook: {
      url: '',
      secret: ''
    },
    result_mode: 'auto'
  })

  // 文件上传状态
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const [showUploadFlow, setShowUploadFlow] = useState(false)

  useEffect(() => {
    if (user) {
      loadJobs()
      loadDirectories()
    }
  }, [user])


  const loadJobs = async (showLoading = true) => {
    try {
      if (showLoading) {
        setIsLoading(true)
      }
      
      const response = await api.listJobs({ 
        page_size: 50,
        job_type: 'kb_management' // 只获取知识库任务
      })
      setJobs(response?.jobs || [])
    } catch (error) {
      console.error('Failed to load jobs:', error)
      if (showLoading) {
        toast.error('加载任务列表失败')
      }
    } finally {
      if (showLoading) {
        setIsLoading(false)
      }
    }
  }

  const loadDirectories = async () => {
    try {
      const response = await api.getDirectories()
      const dirs = response || []
      setDirectories(dirs)
      
      // 设置默认目录
      if (dirs.length > 0) {
        setCreateForm(prev => ({
          ...prev,
          parsing_params: {
            ...prev.parsing_params,
            kb_dir: dirs[0].title
          }
        }))
      }
    } catch (error) {
      console.error('Failed to load directories:', error)
    }
  }

  const loadJobStatus = async (jobId: string) => {
    try {
      const status = await api.getJobStatus(jobId)
      setJobStatus(status)
    } catch (error) {
      console.error('Failed to load job status:', error)
      toast.error('加载任务状态失败')
    }
  }

  const handleCreateJob = async () => {
    try {
      if (createForm.source_type === 'file') {
        if (!selectedFile) {
          toast.error('请选择要上传的文件')
          return
        }
        
        // 显示上传流程组件
        setShowUploadFlow(true)
        return
      } else {
        // URL模式
        if (!createForm.source_url) {
          toast.error('请输入文件URL')
          return
        }

        const jobCreate: JobCreate = {
          source_type: 'url',
          source_url: createForm.source_url,
          data_id: createForm.data_id || undefined,
          parsing_params: createForm.parsing_params,
          webhook: createForm.webhook.url ? createForm.webhook : undefined,
          result_mode: createForm.result_mode
        }

        await api.createJob(jobCreate)
        toast.success('任务创建成功')
        setShowCreateDialog(false)
        resetForm()
        loadJobs()
      }
    } catch (error) {
      console.error('Failed to create job:', error)
      toast.error('创建任务失败')
    }
  }

  const handleUploadSuccess = (job: JobResponse) => {
    toast.success('文件上传成功，任务已创建')
    setShowUploadFlow(false)
    setShowCreateDialog(false)
    resetForm()
    loadJobs()
  }

  const handleUploadError = (error: string) => {
    toast.error(`上传失败: ${error}`)
    setShowUploadFlow(false)
  }

  const resetForm = () => {
    setCreateForm({
      source_type: 'file',
      source_url: '',
      data_id: '',
      parsing_params: {
        kb_dir: directories[0]?.title || '',
        doc_type: 'auto',
        smart_title_parse: true,
        summary_image: false,
        summary_table: true,
        summary_txt: true,
        add_frag_desc: ''
      },
      webhook: {
        url: '',
        secret: ''
      },
      result_mode: 'auto'
    })
    setSelectedFile(null)
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
      const allowedTypes = ['.pdf', '.doc', '.docx', '.txt', '.md', '.xlsx', '.xls', '.csv']
      const fileExtension = '.' + file.name.split('.').pop()?.toLowerCase()
      
      if (allowedTypes.includes(fileExtension)) {
        setSelectedFile(file)
        setCreateForm(prev => ({ ...prev, source_type: 'file' }))
      } else {
        toast.error('不支持的文件格式，请选择 PDF, DOC, DOCX, TXT, MD, XLSX, XLS, CSV 格式的文件')
      }
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'done':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" />
      case 'running':
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
      case 'pending':
        return <Clock className="h-4 w-4 text-yellow-500" />
      case 'waiting_for_upload':
        return <Upload className="h-4 w-4 text-blue-500" />
      default:
        return <AlertCircle className="h-4 w-4 text-gray-500" />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'done':
        return 'bg-green-100 text-green-800'
      case 'failed':
        return 'bg-red-100 text-red-800'
      case 'running':
        return 'bg-blue-100 text-blue-800'
      case 'pending':
        return 'bg-yellow-100 text-yellow-800'
      case 'waiting_for_upload':
        return 'bg-blue-100 text-blue-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case 'waiting_for_upload':
        return '等待上传'
      case 'pending':
        return '排队中'
      case 'running':
        return '处理中'
      case 'done':
        return '已完成'
      case 'failed':
        return '失败'
      default:
        return status
    }
  }

  const filteredJobs = jobs.filter(job => {
    const matchesSearch = job.job_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         job.data_id?.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesStatus = statusFilter === 'all' || job.status === statusFilter
    return matchesSearch && matchesStatus
  })

  if (!user) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">请先登录</p>
      </div>
    )
  }

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
          <h1 className="text-3xl font-bold tracking-tight">任务管理</h1>
          <p className="text-muted-foreground">
            管理您的知识库处理任务，监控任务状态和进度
          </p>
        </div>
        <Button onClick={() => setShowCreateDialog(true)}>
          <Plus className="mr-2 h-4 w-4" />
          创建任务
        </Button>
      </div>


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
            <SelectItem value="waiting_for_upload">等待上传</SelectItem>
            <SelectItem value="pending">排队中</SelectItem>
            <SelectItem value="running">处理中</SelectItem>
            <SelectItem value="done">已完成</SelectItem>
            <SelectItem value="failed">失败</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" onClick={() => loadJobs()} disabled={isLoading}>
          <RefreshCw className="mr-2 h-4 w-4" />
          刷新
        </Button>
      </div>

      {/* 任务列表 */}
      {filteredJobs.length === 0 ? (
        <EmptyState
          icon={<Upload className="h-12 w-12" />}
          title="暂无任务"
          description="您还没有创建任何知识库处理任务"
          action={{
            label: "创建第一个任务",
            onClick: () => setShowCreateDialog(true)
          }}
        />
      ) : (
        <div className="space-y-4">
          {filteredJobs.map((job) => (
            <Card key={job.job_id} className="hover:shadow-md transition-shadow">
              <CardContent className="p-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center space-x-3 mb-3">
                      {getStatusIcon(job.status)}
                      <h3 className="font-medium text-lg">{job.job_id}</h3>
                      <Badge className={getStatusColor(job.status)}>
                        {getStatusText(job.status)}
                      </Badge>
                      {job.data_id && (
                        <span className="text-sm text-muted-foreground">
                          ID: {job.data_id}
                        </span>
                      )}
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-muted-foreground">
                      <div>
                        <p><strong>源类型:</strong> {job.source_type}</p>
                        <p><strong>知识库目录:</strong> N/A</p>
                        <p><strong>结果模式:</strong> {job.result_mode}</p>
                      </div>
                      <div>
                        <p><strong>创建时间:</strong> {formatDate(job.created_at)}</p>
                        {job.error && (
                          <p className="text-red-600"><strong>错误:</strong> {JSON.stringify(job.error)}</p>
                        )}
                      </div>
                    </div>

                    {/* 进度条 */}
                    {job.status === 'running' && job.progress && (
                      <div className="mt-4 space-y-2">
                        <div className="flex justify-between text-sm">
                          <span>处理进度</span>
                          <span>{Object.values(job.progress).join(' / ')}</span>
                        </div>
                        <Progress value={50} className="h-2" />
                      </div>
                    )}
                  </div>
                  
                  <div className="flex items-center space-x-2 ml-4">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setSelectedJob(job)
                        loadJobStatus(job.job_id)
                      }}
                    >
                      <Eye className="mr-1 h-3 w-3" />
                      查看详情
                    </Button>
                    {job.status === 'done' && (job.result_url || job.result) && (
                      <Button
                        size="sm"
                        onClick={() => {
                          if (job.result_url) {
                            window.open(job.result_url, '_blank')
                          } else {
                            // 处理内联结果
                            const blob = new Blob([JSON.stringify(job.result, null, 2)], { type: 'application/json' })
                            const url = URL.createObjectURL(blob)
                            const a = document.createElement('a')
                            a.href = url
                            a.download = `${job.job_id}_result.json`
                            a.click()
                            URL.revokeObjectURL(url)
                          }
                        }}
                      >
                        <Download className="mr-1 h-3 w-3" />
                        下载结果
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
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>创建知识库处理任务</DialogTitle>
            <DialogDescription>
              创建异步任务来处理文档，支持URL和直接上传两种方式
            </DialogDescription>
          </DialogHeader>
          
          {showUploadFlow && selectedFile ? (
            <FileUploadFlow
              file={selectedFile}
              parsingParams={createForm.parsing_params}
              dataId={createForm.data_id || undefined}
              webhook={createForm.webhook.url ? createForm.webhook : undefined}
              resultMode={createForm.result_mode}
              onSuccess={handleUploadSuccess}
              onError={handleUploadError}
              onCancel={() => setShowUploadFlow(false)}
            />
          ) : (
            <div className="space-y-4">
              {/* 源类型选择 */}
              <div>
                <Label htmlFor="source_type">源类型</Label>
                <Select
                  value={createForm.source_type}
                  onValueChange={(value: 'file' | 'url') => 
                    setCreateForm({ ...createForm, source_type: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="file">文件上传</SelectItem>
                    <SelectItem value="url">URL链接</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              {createForm.source_type === 'url' ? (
                <div>
                  <Label htmlFor="source_url">文件URL</Label>
                  <Input
                    id="source_url"
                    placeholder="https://example.com/document.pdf"
                    value={createForm.source_url}
                    onChange={(e) => setCreateForm({ ...createForm, source_url: e.target.value })}
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

              {/* 知识库配置 */}
              <div className="space-y-4 border-t pt-4">
                <h4 className="font-medium">知识库配置</h4>
                
                <div>
                  <Label htmlFor="kb_dir">知识库目录</Label>
                  <Select
                    value={createForm.parsing_params.kb_dir}
                    onValueChange={(value) => setCreateForm({
                      ...createForm,
                      parsing_params: { ...createForm.parsing_params, kb_dir: value }
                    })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="选择目录" />
                    </SelectTrigger>
                    <SelectContent>
                      {directories.map((dir) => (
                        <SelectItem key={dir.id} value={dir.title}>
                          {dir.title}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor="doc_type">文档类型</Label>
                  <Select
                    value={createForm.parsing_params.doc_type || 'auto'}
                    onValueChange={(value) => setCreateForm({
                      ...createForm,
                      parsing_params: { ...createForm.parsing_params, doc_type: value as any }
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
                      checked={createForm.parsing_params.smart_title_parse}
                      onCheckedChange={(checked) => setCreateForm({
                        ...createForm,
                        parsing_params: { ...createForm.parsing_params, smart_title_parse: checked }
                      })}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label htmlFor="summary_image">图像摘要</Label>
                    <Switch
                      id="summary_image"
                      checked={createForm.parsing_params.summary_image}
                      onCheckedChange={(checked) => setCreateForm({
                        ...createForm,
                        parsing_params: { ...createForm.parsing_params, summary_image: checked }
                      })}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label htmlFor="summary_table">表格摘要</Label>
                    <Switch
                      id="summary_table"
                      checked={createForm.parsing_params.summary_table}
                      onCheckedChange={(checked) => setCreateForm({
                        ...createForm,
                        parsing_params: { ...createForm.parsing_params, summary_table: checked }
                      })}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label htmlFor="summary_txt">文本摘要</Label>
                    <Switch
                      id="summary_txt"
                      checked={createForm.parsing_params.summary_txt}
                      onCheckedChange={(checked) => setCreateForm({
                        ...createForm,
                        parsing_params: { ...createForm.parsing_params, summary_txt: checked }
                      })}
                    />
                  </div>
                </div>

                <div>
                  <Label htmlFor="add_frag_desc">额外描述</Label>
                  <Textarea
                    id="add_frag_desc"
                    placeholder="针对文档的人工描述..."
                    value={createForm.parsing_params.add_frag_desc}
                    onChange={(e) => setCreateForm({
                      ...createForm,
                      parsing_params: { ...createForm.parsing_params, add_frag_desc: e.target.value }
                    })}
                  />
                </div>
              </div>

              {/* 可选配置 */}
              <div className="space-y-4 border-t pt-4">
                <h4 className="font-medium">可选配置</h4>
                
                <div>
                  <Label htmlFor="data_id">自定义ID</Label>
                  <Input
                    id="data_id"
                    placeholder="可选，用于标识您的业务数据"
                    value={createForm.data_id}
                    onChange={(e) => setCreateForm({ ...createForm, data_id: e.target.value })}
                  />
                </div>

                <div>
                  <Label htmlFor="webhook_url">Webhook URL</Label>
                  <Input
                    id="webhook_url"
                    placeholder="https://your-webhook.com/callback"
                    value={createForm.webhook.url}
                    onChange={(e) => setCreateForm({
                      ...createForm,
                      webhook: { ...createForm.webhook, url: e.target.value }
                    })}
                  />
                </div>

                <div>
                  <Label htmlFor="webhook_secret">Webhook Secret</Label>
                  <Input
                    id="webhook_secret"
                    placeholder="用于验证Webhook的密钥"
                    value={createForm.webhook.secret}
                    onChange={(e) => setCreateForm({
                      ...createForm,
                      webhook: { ...createForm.webhook, secret: e.target.value }
                    })}
                  />
                </div>

                <div>
                  <Label htmlFor="result_mode">结果返回模式</Label>
                  <Select
                    value={createForm.result_mode}
                    onValueChange={(value: 'auto' | 'inline' | 'url') => 
                      setCreateForm({ ...createForm, result_mode: value })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">自动（推荐）</SelectItem>
                      <SelectItem value="inline">内联返回</SelectItem>
                      <SelectItem value="url">URL下载</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex justify-end space-x-2">
                <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
                  取消
                </Button>
                <Button onClick={handleCreateJob} disabled={!selectedFile && createForm.source_type === 'file'}>
                  {createForm.source_type === 'file' ? '开始上传' : '创建任务'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* 任务详情对话框 */}
      <Dialog open={!!selectedJob} onOpenChange={() => setSelectedJob(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>任务详情</DialogTitle>
            <DialogDescription>
              查看任务的详细信息和处理进度
            </DialogDescription>
          </DialogHeader>
          {selectedJob && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-sm font-medium text-muted-foreground">任务ID</Label>
                  <p className="text-sm font-mono">{selectedJob.job_id}</p>
                </div>
                <div>
                  <Label className="text-sm font-medium text-muted-foreground">状态</Label>
                  <div className="flex items-center space-x-2">
                    {getStatusIcon(selectedJob.status)}
                    <Badge className={getStatusColor(selectedJob.status)}>
                      {getStatusText(selectedJob.status)}
                    </Badge>
                  </div>
                </div>
                <div>
                  <Label className="text-sm font-medium text-muted-foreground">来源类型</Label>
                  <p className="text-sm">{selectedJob.source_type}</p>
                </div>
                <div>
                  <Label className="text-sm font-medium text-muted-foreground">结果模式</Label>
                  <p className="text-sm">{selectedJob.result_mode}</p>
                </div>
              </div>
              
              {jobStatus && (
                <div className="space-y-4">
                  <div>
                    <Label className="text-sm font-medium text-muted-foreground">当前状态</Label>
                    <p className="text-sm">{jobStatus.current_state || 'N/A'}</p>
                  </div>
                  
                  {jobStatus.progress && (
                    <div>
                      <Label className="text-sm font-medium text-muted-foreground">处理进度</Label>
                      <div className="mt-2 space-y-2">
                        {Object.entries(jobStatus.progress).map(([key, value]) => (
                          <div key={key} className="flex items-center justify-between text-sm">
                            <span>{key}</span>
                            <span className="text-muted-foreground">{String(value)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {(jobStatus.result_url || jobStatus.result) && (
                    <div>
                      <Button
                        onClick={() => {
                          if (jobStatus.result_url) {
                            window.open(jobStatus.result_url, '_blank')
                          } else {
                            const blob = new Blob([JSON.stringify(jobStatus.result, null, 2)], { type: 'application/json' })
                            const url = URL.createObjectURL(blob)
                            const a = document.createElement('a')
                            a.href = url
                            a.download = `${selectedJob.job_id}_result.json`
                            a.click()
                            URL.revokeObjectURL(url)
                          }
                        }}
                        className="w-full"
                      >
                        <Download className="mr-2 h-4 w-4" />
                        下载结果
                      </Button>
                    </div>
                  )}
                </div>
              )}
              
              {selectedJob.error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                  <Label className="text-sm font-medium text-red-600">错误信息</Label>
                  <p className="text-sm text-red-600 mt-1">{JSON.stringify(selectedJob.error)}</p>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
