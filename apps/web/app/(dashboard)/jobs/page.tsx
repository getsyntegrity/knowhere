"use client"

import { useState, useEffect } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { api, JobResponse, JobStatus, JobCreate } from '@/lib/api'
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
  Loader2,
  ChevronDown,
  ChevronRight
} from 'lucide-react'
import { formatDate } from '@/lib/format'
import { getAllSupportedExtensions, getFileTypeDisplayName } from '@/lib/constants'

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
  const [confirmingUpload, setConfirmingUpload] = useState<Record<string, boolean>>({})
  // 创建任务表单状态
  const [createForm, setCreateForm] = useState<{
    source_type: 'file' | 'url'
    source_url: string
    data_id: string
    webhook: {
      url: string
      secret: string
    }
    result_mode: 'auto' | 'inline' | 'url'
    parsing_params: {
      model: 'base' | 'advanced'
      ocr_enabled: boolean
      kb_dir: string
      doc_type: 'auto' | 'pdf' | 'docx' | 'txt' | 'md'
      smart_title_parse: boolean
      summary_image: boolean
      summary_table: boolean
      summary_txt: boolean
      add_frag_desc: string
    }
  }>({
    source_type: 'file',
    source_url: '',
    data_id: '',
    webhook: {
      url: '',
      secret: ''
    },
    result_mode: 'auto',
    parsing_params: {
      model: 'base',
      ocr_enabled: false,
      kb_dir: '默认目录',
      doc_type: 'auto',
      smart_title_parse: true,
      summary_image: false,
      summary_table: true,
      summary_txt: true,
      add_frag_desc: ''
    }
  })

  // 文件上传状态
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const [showUploadFlow, setShowUploadFlow] = useState(false)
  
  // 解析参数区域展开状态
  const [showParsingParams, setShowParsingParams] = useState(false)
  // 可选配置区域展开状态
  const [showOptionalConfig, setShowOptionalConfig] = useState(false)

  useEffect(() => {
    if (user) {
      loadJobs()
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


  const loadJobStatus = async (jobId: string) => {
    try {
      const status = await api.getJobStatus(jobId)
      setJobStatus(status)
    } catch (error) {
      console.error('Failed to load job status:', error)
      toast.error('加载任务状态失败')
    }
  }

  const handleConfirmUpload = async (jobId: string) => {
    try {
      setConfirmingUpload(prev => ({ ...prev, [jobId]: true }))
      
      await api.confirmUpload(jobId)
      
      toast.success('上传确认成功', '任务已开始处理')
      
      // 刷新任务列表
      await loadJobs()
    } catch (error: any) {
      console.error('确认上传失败:', error)
      toast.error('确认上传失败', error.message || '请稍后重试')
    } finally {
      setConfirmingUpload(prev => ({ ...prev, [jobId]: false }))
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
      webhook: {
        url: '',
        secret: ''
      },
      result_mode: 'auto',
      parsing_params: {
        model: 'base',
        ocr_enabled: false,
        kb_dir: '默认目录',
        doc_type: 'auto',
        smart_title_parse: true,
        summary_image: false,
        summary_table: true,
        summary_txt: true,
        add_frag_desc: ''
      }
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
      const allowedTypes = getAllSupportedExtensions()
      const fileExtension = '.' + file.name.split('.').pop()?.toLowerCase()
      
      if (allowedTypes.includes(fileExtension)) {
        setSelectedFile(file)
        setCreateForm(prev => ({ ...prev, source_type: 'file' }))
      } else {
        const supportedFormats = allowedTypes.join(', ')
        toast.error(`不支持的文件格式，请选择以下格式的文件：${supportedFormats}`)
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
      case 'waiting-file':
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
      case 'waiting-file':
        return 'bg-blue-100 text-blue-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case 'waiting-file':
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
            <SelectItem value="waiting-file">等待上传</SelectItem>
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
                    {(job.status === 'waiting-file' || job.status === 'pending') && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleConfirmUpload(job.job_id)}
                        disabled={confirmingUpload[job.job_id]}
                      >
                        {confirmingUpload[job.job_id] ? (
                          <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            确认中...
                          </>
                        ) : (
                          <>
                            <CheckCircle className="mr-2 h-4 w-4" />
                            确认上传
                          </>
                        )}
                      </Button>
                    )}
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
              dataId={createForm.data_id || undefined}
              parsingParams={createForm.parsing_params}
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
                      accept={getAllSupportedExtensions().join(',')}
                      onChange={(e) => {
                        const file = e.target.files?.[0] || null
                        if (file) {
                          const allowedTypes = getAllSupportedExtensions()
                          const fileExtension = '.' + file.name.split('.').pop()?.toLowerCase()
                          
                          if (allowedTypes.includes(fileExtension)) {
                            setSelectedFile(file)
                          } else {
                            const supportedFormats = allowedTypes.join(', ')
                            toast.error(`不支持的文件格式，请选择以下格式的文件：${supportedFormats}`)
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
                          支持 {getAllSupportedExtensions().join(', ')} 格式
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* 解析参数配置 */}
              <div className="space-y-4 border-t pt-4">
                <button
                  type="button"
                  onClick={() => setShowParsingParams(!showParsingParams)}
                  className="flex items-center justify-between w-full text-left hover:bg-gray-50 p-2 rounded-md transition-colors"
                >
                  <h4 className="font-medium">解析参数配置</h4>
                  {showParsingParams ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </button>
                
                {showParsingParams && (
                  <div className="space-y-4 pl-4 border-l-2 border-gray-200">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor="model">解析模型</Label>
                        <Select
                          value={createForm.parsing_params.model}
                          onValueChange={(value: 'base' | 'advanced') => 
                            setCreateForm({
                              ...createForm,
                              parsing_params: { ...createForm.parsing_params, model: value }
                            })
                          }
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="base">基础模型</SelectItem>
                            <SelectItem value="advanced">高级模型</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label htmlFor="kb_dir">知识库目录</Label>
                        <Input
                          id="kb_dir"
                          placeholder="默认目录"
                          value={createForm.parsing_params.kb_dir}
                          onChange={(e) => setCreateForm({
                            ...createForm,
                            parsing_params: { ...createForm.parsing_params, kb_dir: e.target.value }
                          })}
                        />
                      </div>

                      <div>
                        <Label htmlFor="doc_type">文档类型</Label>
                        <Select
                          value={createForm.parsing_params.doc_type}
                          onValueChange={(value: 'auto' | 'pdf' | 'docx' | 'txt' | 'md') => 
                            setCreateForm({
                              ...createForm,
                              parsing_params: { ...createForm.parsing_params, doc_type: value }
                            })
                          }
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="auto">自动检测</SelectItem>
                            <SelectItem value="pdf">PDF</SelectItem>
                            <SelectItem value="docx">Word文档</SelectItem>
                            <SelectItem value="txt">文本文件</SelectItem>
                            <SelectItem value="md">Markdown</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label htmlFor="add_frag_desc">片段描述</Label>
                        <Input
                          id="add_frag_desc"
                          placeholder="可选，添加片段描述"
                          value={createForm.parsing_params.add_frag_desc}
                          onChange={(e) => setCreateForm({
                            ...createForm,
                            parsing_params: { ...createForm.parsing_params, add_frag_desc: e.target.value }
                          })}
                        />
                      </div>
                    </div>

                    <div className="space-y-3">
                      <div className="flex items-center space-x-2">
                        <Switch
                          id="ocr_enabled"
                          checked={createForm.parsing_params.ocr_enabled}
                          onCheckedChange={(checked) => setCreateForm({
                            ...createForm,
                            parsing_params: { ...createForm.parsing_params, ocr_enabled: checked }
                          })}
                        />
                        <Label htmlFor="ocr_enabled">启用OCR识别</Label>
                      </div>

                      <div className="flex items-center space-x-2">
                        <Switch
                          id="smart_title_parse"
                          checked={createForm.parsing_params.smart_title_parse}
                          onCheckedChange={(checked) => setCreateForm({
                            ...createForm,
                            parsing_params: { ...createForm.parsing_params, smart_title_parse: checked }
                          })}
                        />
                        <Label htmlFor="smart_title_parse">智能标题解析</Label>
                      </div>

                      <div className="flex items-center space-x-2">
                        <Switch
                          id="summary_image"
                          checked={createForm.parsing_params.summary_image}
                          onCheckedChange={(checked) => setCreateForm({
                            ...createForm,
                            parsing_params: { ...createForm.parsing_params, summary_image: checked }
                          })}
                        />
                        <Label htmlFor="summary_image">生成图片摘要</Label>
                      </div>

                      <div className="flex items-center space-x-2">
                        <Switch
                          id="summary_table"
                          checked={createForm.parsing_params.summary_table}
                          onCheckedChange={(checked) => setCreateForm({
                            ...createForm,
                            parsing_params: { ...createForm.parsing_params, summary_table: checked }
                          })}
                        />
                        <Label htmlFor="summary_table">生成表格摘要</Label>
                      </div>

                      <div className="flex items-center space-x-2">
                        <Switch
                          id="summary_txt"
                          checked={createForm.parsing_params.summary_txt}
                          onCheckedChange={(checked) => setCreateForm({
                            ...createForm,
                            parsing_params: { ...createForm.parsing_params, summary_txt: checked }
                          })}
                        />
                        <Label htmlFor="summary_txt">生成文本摘要</Label>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* 可选配置 */}
              <div className="space-y-4 border-t pt-4">
                <button
                  type="button"
                  onClick={() => setShowOptionalConfig(!showOptionalConfig)}
                  className="flex items-center justify-between w-full text-left hover:bg-gray-50 p-2 rounded-md transition-colors"
                >
                  <h4 className="font-medium">可选配置</h4>
                  {showOptionalConfig ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </button>
                
                {showOptionalConfig && (
                  <div className="space-y-4 pl-4 border-l-2 border-gray-200">
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
                )}
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
