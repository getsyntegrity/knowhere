"use client"

import { useState, useEffect } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { api } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Progress } from '@/components/ui/progress'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { EmptyState } from '@/components/common/EmptyState'
import { 
  Plus, 
  Search, 
  Upload, 
  FileText, 
  FileSpreadsheet,
  Trash2,
  Download,
  RefreshCw,
  Eye,
  Play,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle
} from 'lucide-react'
import { formatDate } from '@/lib/format'
import type { TableFillJobResponse, TableFillJobStatus, TableFillJobCreateRequest } from '@/lib/api'

export default function TableDocsPage() {
  const { user } = useAuth()
  const toast = useToast()
  const [jobs, setJobs] = useState<TableFillJobResponse[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [selectedJob, setSelectedJob] = useState<TableFillJobResponse | null>(null)
  const [jobStatus, setJobStatus] = useState<TableFillJobStatus | null>(null)

  // 创建任务表单状态
  const [createForm, setCreateForm] = useState<TableFillJobCreateRequest>({
    source_type: 'file_upload',
    file_url: '',
    webhook_url: '',
    metadata: {}
  })

  // 文件上传状态
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)

  useEffect(() => {
    loadJobs()
  }, [currentPage, statusFilter])

  const loadJobs = async () => {
    try {
      setIsLoading(true)
      const response = await api.listTableFillJobs(
        currentPage,
        20,
        statusFilter === 'all' ? undefined : statusFilter
      )
      setJobs(response.jobs)
      setTotalPages(Math.ceil(response.total / 20))
    } catch (error) {
      console.error('Failed to load jobs:', error)
      toast.error('加载任务列表失败')
    } finally {
      setIsLoading(false)
    }
  }

  const loadJobStatus = async (jobId: string) => {
    try {
      const status = await api.getTableFillJobStatus(jobId)
      setJobStatus(status)
    } catch (error) {
      console.error('Failed to load job status:', error)
      toast.error('加载任务状态失败')
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
      const allowedTypes = ['.xlsx', '.xls', '.csv', '.pdf', '.doc', '.docx']
      const fileExtension = '.' + file.name.split('.').pop()?.toLowerCase()
      
      if (allowedTypes.includes(fileExtension)) {
        setSelectedFile(file)
        setCreateForm({ ...createForm, source_type: 'file_upload' })
      } else {
        toast.error('不支持的文件格式，请选择 XLSX, XLS, CSV, PDF, DOC, DOCX 格式的文件')
      }
    }
  }

  const handleCreateJob = async () => {
    try {
      setIsUploading(true)
      
      if (createForm.source_type === 'file_upload') {
        if (!selectedFile) {
          toast.error('请选择要上传的文件')
          return
        }
        
        // 使用文件上传接口
        await api.uploadFileAndCreateTableFillJob(selectedFile, createForm.webhook_url, createForm.metadata)
      } else if (createForm.source_type === 'url') {
        if (!createForm.file_url) {
          toast.error('请输入文件URL')
          return
        }
        await api.createTableFillJob(createForm)
      }

      toast.success('表格填充任务创建成功')
      setShowCreateDialog(false)
      setCreateForm({
        source_type: 'file_upload',
        file_url: '',
        webhook_url: '',
        metadata: {}
      })
      setSelectedFile(null)
      loadJobs()
    } catch (error) {
      console.error('Failed to create job:', error)
      toast.error('创建任务失败')
    } finally {
      setIsUploading(false)
    }
  }

  const handleDownloadResult = async (jobId: string) => {
    try {
      const response = await api.downloadTableFillResult(jobId)
      window.open(response.download_url, '_blank')
    } catch (error) {
      console.error('Failed to download result:', error)
      toast.error('下载结果失败')
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" />
      case 'processing':
        return <Clock className="h-4 w-4 text-blue-500" />
      case 'pending':
        return <AlertCircle className="h-4 w-4 text-yellow-500" />
      default:
        return <Clock className="h-4 w-4 text-gray-500" />
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge variant="default" className="bg-green-500">已完成</Badge>
      case 'failed':
        return <Badge variant="destructive">失败</Badge>
      case 'processing':
        return <Badge variant="default" className="bg-blue-500">处理中</Badge>
      case 'pending':
        return <Badge variant="secondary">等待中</Badge>
      default:
        return <Badge variant="outline">未知</Badge>
    }
  }

  const getCurrentStateText = (currentState?: string) => {
    const stateMap: Record<string, string> = {
      'uploading': '上传文件中',
      'uploaded': '文件上传完成',
      'extracting_table': '提取表格中',
      'table_extracted': '表格提取完成',
      'kb_searching': '检索知识库中',
      'kb_searched': '知识库检索完成',
      'llm_processing': 'LLM处理中',
      'llm_processed': 'LLM处理完成',
      'filling_table': '填充表格中',
      'table_filled': '表格填充完成',
      'generating_result': '生成结果中',
      'completed': '任务完成',
      'failed': '任务失败'
    }
    return stateMap[currentState || ''] || currentState || '未知状态'
  }

  const getProgressPercentage = (currentState?: string) => {
    const stateProgress: Record<string, number> = {
      'pending': 5,
      'uploading': 15,
      'uploaded': 20,
      'extracting_table': 35,
      'table_extracted': 40,
      'kb_searching': 55,
      'kb_searched': 60,
      'llm_processing': 75,
      'llm_processed': 80,
      'filling_table': 90,
      'table_filled': 95,
      'generating_result': 98,
      'completed': 100,
      'failed': 0
    }
    return stateProgress[currentState || ''] || 0
  }

  const getFileIcon = (filename: string) => {
    const extension = filename.split('.').pop()?.toLowerCase()
    switch (extension) {
      case 'xlsx':
      case 'xls':
        return <FileSpreadsheet className="h-8 w-8 text-green-500" />
      case 'csv':
        return <FileText className="h-8 w-8 text-blue-500" />
      case 'pdf':
        return <FileText className="h-8 w-8 text-red-500" />
      case 'doc':
      case 'docx':
        return <FileText className="h-8 w-8 text-blue-600" />
      default:
        return <FileText className="h-8 w-8 text-gray-500" />
    }
  }

  const getFileTypeBadge = (filename: string) => {
    const extension = filename.split('.').pop()?.toLowerCase()
    const typeMap: Record<string, string> = {
      'xlsx': 'Excel',
      'xls': 'Excel',
      'csv': 'CSV',
      'pdf': 'PDF',
      'doc': 'Word',
      'docx': 'Word'
    }
    return typeMap[extension || ''] || extension?.toUpperCase() || 'Unknown'
  }

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return 'N/A'
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`
  }

  const getDocumentInfo = (job: TableFillJobResponse) => {
    const metadata = job.job_metadata || {}
    const filename = metadata.original_filename || job.file_path?.split('/').pop() || job.s3_key?.split('/').pop() || 'Unknown'
    const fileSize = metadata.file_size
    return { filename, fileSize }
  }

  const filteredJobs = jobs.filter(job => {
    const { filename } = getDocumentInfo(job)
    const matchesSearch = job.job_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         job.current_state?.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesStatus = statusFilter === 'all' || job.status === statusFilter
    return matchesSearch && matchesStatus
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 页面标题和操作 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">表格填充任务</h1>
          <p className="text-muted-foreground">
            管理您的表格填充任务，查看任务状态和下载结果
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Button onClick={() => setShowCreateDialog(true)}>
            <Plus className="mr-2 h-4 w-4" />
            创建任务
          </Button>
          <Button variant="outline" onClick={loadJobs}>
            <RefreshCw className="mr-2 h-4 w-4" />
            刷新
          </Button>
        </div>
      </div>

      {/* 搜索和过滤 */}
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
            <SelectValue placeholder="状态过滤" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="pending">等待中</SelectItem>
            <SelectItem value="processing">处理中</SelectItem>
            <SelectItem value="completed">已完成</SelectItem>
            <SelectItem value="failed">失败</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* 任务列表 */}
      {filteredJobs.length === 0 ? (
        <EmptyState
          icon={<Clock className="h-12 w-12" />}
          title="暂无表格填充任务"
          description="创建您的第一个表格填充任务"
          action={
            <Button onClick={() => setShowCreateDialog(true)}>
              <Plus className="mr-2 h-4 w-4" />
              创建任务
            </Button>
          }
        />
      ) : (
        <div className="space-y-4">
          {filteredJobs.map((job) => {
            const { filename, fileSize } = getDocumentInfo(job)
            const progress = getProgressPercentage(job.current_state)
            
            return (
              <Card key={job.job_id} className="hover:shadow-md transition-shadow">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      {getFileIcon(filename)}
                      <div>
                        <CardTitle className="text-lg">{filename}</CardTitle>
                        <CardDescription className="text-sm text-muted-foreground">
                          任务 {job.job_id.slice(0, 8)}
                        </CardDescription>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
                      {getStatusIcon(job.status)}
                      {getStatusBadge(job.status)}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                    <div>
                      <Label className="text-muted-foreground">文件大小</Label>
                      <p>{formatFileSize(fileSize)}</p>
                    </div>
                    <div>
                      <Label className="text-muted-foreground">当前状态</Label>
                      <p>{getCurrentStateText(job.current_state)}</p>
                    </div>
                    <div>
                      <Label className="text-muted-foreground">创建时间</Label>
                      <p>{formatDate(job.created_at, 'relative')}</p>
                    </div>
                  </div>
                  
                  {/* 进度条 */}
                  {job.status === 'processing' && (
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span>处理进度</span>
                        <span>{progress}%</span>
                      </div>
                      <Progress value={progress} className="h-2" />
                    </div>
                  )}
                  
                  {job.error_message && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                      <p className="text-sm text-red-600">{job.error_message}</p>
                    </div>
                  )}
                  
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
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
                      {job.status === 'completed' && job.result_s3_key && (
                        <Button
                          size="sm"
                          onClick={() => handleDownloadResult(job.job_id)}
                        >
                          <Download className="mr-1 h-3 w-3" />
                          下载结果
                        </Button>
                      )}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      更新时间: {formatDate(job.updated_at, 'relative')}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center space-x-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
            disabled={currentPage === 1}
          >
            上一页
          </Button>
          <span className="text-sm text-muted-foreground">
            第 {currentPage} 页，共 {totalPages} 页
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
            disabled={currentPage === totalPages}
          >
            下一页
          </Button>
        </div>
      )}

      {/* 创建任务对话框 */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>创建表格填充任务</DialogTitle>
            <DialogDescription>
              创建异步任务来处理表格文件，支持URL和直接上传两种方式
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="source_type">文件来源类型</Label>
              <Select
                value={createForm.source_type}
                onValueChange={(value: 'file_upload' | 'url') => 
                  setCreateForm({ ...createForm, source_type: value })
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
            
            {createForm.source_type === 'url' ? (
              <div>
                <Label htmlFor="file_url">文件URL</Label>
                <Input
                  id="file_url"
                  placeholder="https://example.com/document.xlsx"
                  value={createForm.file_url}
                  onChange={(e) => setCreateForm({ ...createForm, file_url: e.target.value })}
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
                    accept=".xlsx,.xls,.csv,.pdf,.doc,.docx"
                    onChange={(e) => {
                      const file = e.target.files?.[0] || null
                      if (file) {
                        // 检查文件类型
                        const allowedTypes = ['.xlsx', '.xls', '.csv', '.pdf', '.doc', '.docx']
                        const fileExtension = '.' + file.name.split('.').pop()?.toLowerCase()
                        
                        if (allowedTypes.includes(fileExtension)) {
                          setSelectedFile(file)
                        } else {
                          toast.error('不支持的文件格式，请选择 XLSX, XLS, CSV, PDF, DOC, DOCX 格式的文件')
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
                        支持 XLSX, XLS, CSV, PDF, DOC, DOCX 格式
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
                placeholder="https://your-webhook-url.com"
                value={createForm.webhook_url || ''}
                onChange={(e) => setCreateForm({ ...createForm, webhook_url: e.target.value })}
              />
            </div>
            <div className="flex justify-end space-x-2">
              <Button variant="outline" onClick={() => setShowCreateDialog(false)} disabled={isUploading}>
                取消
              </Button>
              <Button onClick={handleCreateJob} disabled={isUploading}>
                {isUploading ? (
                  <>
                    <LoadingSpinner className="mr-2 h-4 w-4" />
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
                    {getStatusBadge(selectedJob.status)}
                  </div>
                </div>
                <div>
                  <Label className="text-sm font-medium text-muted-foreground">来源类型</Label>
                  <p className="text-sm">{selectedJob.source_type}</p>
                </div>
                <div>
                  <Label className="text-sm font-medium text-muted-foreground">Webhook</Label>
                  <p className="text-sm">{selectedJob.webhook_enabled ? '已启用' : '未启用'}</p>
                </div>
              </div>
              
              {jobStatus && (
                <div className="space-y-4">
                  <div>
                    <Label className="text-sm font-medium text-muted-foreground">当前状态</Label>
                    <p className="text-sm">{getCurrentStateText(jobStatus.current_state)}</p>
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
                  
                  {jobStatus.download_url && (
                    <div>
                      <Button
                        onClick={() => window.open(jobStatus.download_url, '_blank')}
                        className="w-full"
                      >
                        <Download className="mr-2 h-4 w-4" />
                        下载结果
                      </Button>
                    </div>
                  )}
                </div>
              )}
              
              {selectedJob.error_message && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                  <Label className="text-sm font-medium text-red-600">错误信息</Label>
                  <p className="text-sm text-red-600 mt-1">{selectedJob.error_message}</p>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
