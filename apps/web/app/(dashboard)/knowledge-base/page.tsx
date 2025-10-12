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
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { EmptyState } from '@/components/common/EmptyState'
import { 
  Plus, 
  Search, 
  Upload, 
  FileText, 
  FolderOpen,
  Trash2,
  Download,
  RefreshCw,
  X
} from 'lucide-react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { formatDate } from '@/lib/format'

interface KnowledgeBaseItem {
  id: string
  title: string
  parent_id?: string
  user_id: string
  create_time?: string
  update_time?: string
  children?: KnowledgeBaseItem[]
}

interface FileTreeItem {
  name: string
  type: 'file' | 'folder'
  children?: FileTreeItem[]
  path: string
}

interface KBJobResponse {
  job_id: string
  status: string
  current_state?: string
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

export default function KnowledgeBasePage() {
  const { user } = useAuth()
  const { success, error, warning, info, loading } = useToast()
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseItem[]>([])
  const [fileTree, setFileTree] = useState<FileTreeItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedPath, setSelectedPath] = useState('')
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showUploadDialog, setShowUploadDialog] = useState(false)
  // showFragmentDialog 已删除，旧方案碎片API已移除

  // 创建知识库表单状态
  const [createForm, setCreateForm] = useState({
    path: '',
    labels: [''] as string[]
  })

  // 创建任务表单状态
  const [createJobForm, setCreateJobForm] = useState({
    source_type: 'file_upload' as 'file_upload' | 'url',
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

  // 任务状态
  const [jobs, setJobs] = useState<KBJobResponse[]>([])
  const [isCreatingJob, setIsCreatingJob] = useState(false)

  useEffect(() => {
    loadKnowledgeBases()
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
      loadJobs() // 自动刷新，不显示加载状态
    }, 10000) // 增加到10秒刷新一次，减少请求频率

    return () => clearInterval(interval)
  }, [jobs]) // 依赖jobs数组，当任务状态变化时重新评估

  const loadKnowledgeBases = async () => {
    try {
      setIsLoading(true)
      const response = await api.getDirectories()
      const directories = response || []
      setKnowledgeBases(directories)
      
      // 设置默认目录为第一个目录
      if (directories.length > 0) {
        const defaultDir = directories[0].title
        setCreateJobForm(prev => ({
          ...prev,
          metadata: { ...prev.metadata, kb_dir: defaultDir }
        }))
      }
    } catch (e) {
      console.error('Failed to load knowledge bases:', e)
      error('加载知识库失败')
    } finally {
      setIsLoading(false)
    }
  }

  const loadJobs = async () => {
    try {
      const response = await api.getKBJobs({ limit: 20 })
      setJobs(response?.jobs || [])
    } catch (e) {
      console.error('Failed to load jobs:', e)
    }
  }

  // 手动刷新函数
  const handleManualRefresh = () => {
    loadJobs()
  }

  const loadFileTree = async (directoryId: string) => {
    try {
      const response = await api.getDirectoryContents(directoryId)
      // 将知识库内容转换为文件树格式
      const fileTreeItems = (response || []).map((content: any) => ({
        name: content.path?.split(';').pop() || content.id,
        type: 'file' as const,
        path: content.path || content.id,
        content: content
      }))
      setFileTree(fileTreeItems)
    } catch (e) {
      console.error('Failed to load file tree:', e)
      error('加载文件树失败')
    }
  }

  const handleCreateKnowledgeBase = async () => {
    try {
      const labels = createForm.labels.filter(label => label.trim() !== '')
      await api.addKBPath({
        path: createForm.path,
        label: labels
      })
      success('知识库创建成功')
      setShowCreateDialog(false)
      setCreateForm({ path: '', labels: [''] })
      loadKnowledgeBases()
    } catch (e) {
      console.error('Failed to create knowledge base:', e)
      error('创建知识库失败')
    }
  }

  const handleCreateJob = async () => {
    try {
      setIsCreatingJob(true)
      
      if (createJobForm.source_type === 'file_upload') {
        if (!selectedFile) {
          error('请选择要上传的文件')
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
      
      success('任务创建成功')
      setShowUploadDialog(false)
      
      // 重置表单，保持当前选择的目录
      const currentKbDir = createJobForm.metadata.kb_dir
      setCreateJobForm({
        source_type: 'file_upload',
        file_url: '',
        webhook_url: '',
        metadata: {
          doc_type: 'auto',
          kb_dir: currentKbDir,
          smart_title_parse: true,
          summary_image: false,
          summary_table: true,
          summary_txt: true,
          add_frag_desc: ''
        }
      })
      setSelectedFile(null)
      loadJobs()
    } catch (e) {
      console.error('Failed to create job:', e)
      error('创建任务失败')
    } finally {
      setIsCreatingJob(false)
    }
  }

  const handleRetryJob = async (jobId: string) => {
    try {
      await api.retryKBJob(jobId)
      success('任务重试成功')
      loadJobs()
    } catch (e) {
      console.error('Failed to retry job:', e)
      error('重试任务失败')
    }
  }

  const handleCancelJob = async (jobId: string) => {
    try {
      await api.cancelKBJob(jobId)
      success('任务已取消')
      loadJobs()
    } catch (e) {
      console.error('Failed to cancel job:', e)
      error('取消任务失败')
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
        error('不支持的文件格式，请选择 PDF, DOC, DOCX, TXT, MD, XLSX, XLS, CSV 格式的文件')
      }
    }
  }

  const handleDeleteKnowledgeBase = async (contentId: string) => {
    try {
      await api.deleteKBContent(contentId)
      success('删除成功')
      loadKnowledgeBases()
    } catch (e) {
      console.error('Failed to delete knowledge base:', e)
      error('删除知识库失败')
    }
  }

  const filteredKnowledgeBases = knowledgeBases.filter((kb: KnowledgeBaseItem) =>
    kb.title.toLowerCase().includes(searchQuery.toLowerCase())
  )

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
          <h1 className="text-3xl font-bold tracking-tight">知识库管理</h1>
          <p className="text-muted-foreground">
            管理您的知识库内容，上传文档和添加知识碎片
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Button onClick={() => setShowCreateDialog(true)}>
            <Plus className="mr-2 h-4 w-4" />
            创建知识库
          </Button>
          <Button variant="outline" onClick={() => setShowUploadDialog(true)}>
            <Upload className="mr-2 h-4 w-4" />
            创建任务
          </Button>
        </div>
      </div>

      {/* 搜索栏 */}
      <div className="flex items-center space-x-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
          <Input
            placeholder="搜索知识库..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Button variant="outline" onClick={handleManualRefresh}>
          <RefreshCw className="mr-2 h-4 w-4" />
          刷新
        </Button>
      </div>

      {/* 知识库列表 */}
      {filteredKnowledgeBases.length === 0 ? (
        <EmptyState
          icon={<FolderOpen className="h-12 w-12" />}
          title="暂无知识库"
          description="创建您的第一个知识库开始使用"
          action={{
            label: "创建知识库",
            onClick: () => setShowCreateDialog(true)
          }}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredKnowledgeBases.map((kb) => (
            <Card key={kb.id} className="hover:shadow-md transition-shadow">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">{kb.title}</CardTitle>
                  <Badge variant="secondary">directory</Badge>
                </div>
                <CardDescription className="text-sm text-muted-foreground">
                  {kb.title}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                  <span>{kb.children?.length || 0} 个子项</span>
                  <span>{formatDate(kb.create_time || '', 'relative')}</span>
                </div>
                <div className="flex items-center space-x-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setSelectedPath(kb.id)
                      loadFileTree(kb.id)
                    }}
                  >
                    <FolderOpen className="mr-1 h-3 w-3" />
                    查看
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => handleDeleteKnowledgeBase(kb.id)}
                  >
                    <Trash2 className="mr-1 h-3 w-3" />
                    删除
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* 任务管理区域 */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">任务管理</h2>
          <Button variant="outline" onClick={loadJobs}>
            <RefreshCw className="mr-2 h-4 w-4" />
            刷新
          </Button>
        </div>
        
        {jobs.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-8">
              <FileText className="h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium mb-2">暂无任务</h3>
              <p className="text-muted-foreground text-center mb-4">
                您还没有创建任何知识库处理任务
              </p>
              <Button onClick={() => setShowUploadDialog(true)}>
                <Plus className="mr-2 h-4 w-4" />
                创建第一个任务
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {jobs.map((job) => (
              <Card key={job.job_id}>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2 mb-2">
                        <h3 className="font-medium">{job.job_id}</h3>
                        <span className={`px-2 py-1 rounded-full text-xs ${
                          job.status === 'completed' ? 'bg-green-100 text-green-800' :
                          job.status === 'failed' ? 'bg-red-100 text-red-800' :
                          job.status === 'running' ? 'bg-blue-100 text-blue-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {job.status}
                        </span>
                        <span className="text-sm text-muted-foreground">
                          {job.current_state}
                        </span>
                      </div>
                      <div className="text-sm text-muted-foreground">
                        <p>源类型: {job.source_type}</p>
                        {job.file_path && <p>文件路径: {job.file_path}</p>}
                        {job.s3_key && <p>S3键: {job.s3_key}</p>}
                        <p>创建时间: {new Date(job.created_at).toLocaleString()}</p>
                        {job.error_message && (
                          <p className="text-red-600">错误: {job.error_message}</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
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
      </div>

      {/* 创建知识库对话框 */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>创建知识库</DialogTitle>
            <DialogDescription>
              创建一个新的知识库路径，用于组织您的文档和知识内容
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="path">知识库路径</Label>
              <Input
                id="path"
                placeholder="/documents/my-knowledge-base"
                value={createForm.path}
                onChange={(e) => setCreateForm({ ...createForm, path: e.target.value })}
              />
            </div>
            <div>
              <Label>标签</Label>
              <div className="space-y-2">
                {createForm.labels.map((label, index) => (
                  <Input
                    key={index}
                    placeholder={`标签 ${index + 1}`}
                    value={label}
                    onChange={(e) => {
                      const newLabels = [...createForm.labels]
                      newLabels[index] = e.target.value
                      setCreateForm({ ...createForm, labels: newLabels })
                    }}
                  />
                ))}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setCreateForm({
                    ...createForm,
                    labels: [...createForm.labels, '']
                  })}
                >
                  <Plus className="mr-1 h-3 w-3" />
                  添加标签
                </Button>
              </div>
            </div>
            <div className="flex justify-end space-x-2">
              <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
                取消
              </Button>
              <Button onClick={handleCreateKnowledgeBase}>
                创建
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* 创建任务对话框 */}
      <Dialog open={showUploadDialog} onOpenChange={setShowUploadDialog}>
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
                          error('不支持的文件格式，请选择 PDF, DOC, DOCX, TXT, MD, XLSX, XLS, CSV 格式的文件')
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
                <Select
                  value={createJobForm.metadata.kb_dir}
                  onValueChange={(value) => setCreateJobForm({
                    ...createJobForm,
                    metadata: { ...createJobForm.metadata, kb_dir: value }
                  })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="选择目录" />
                  </SelectTrigger>
                  <SelectContent>
                    {knowledgeBases.map((kb) => (
                      <SelectItem key={kb.id} value={kb.title}>
                        {kb.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label htmlFor="doc_type">文档类型</Label>
                <Select
                  value={createJobForm.metadata.doc_type}
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
                    checked={createJobForm.metadata.smart_title_parse}
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
                    checked={createJobForm.metadata.summary_image}
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
                    checked={createJobForm.metadata.summary_table}
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
                    checked={createJobForm.metadata.summary_txt}
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
                  value={createJobForm.metadata.add_frag_desc}
                  onChange={(e) => setCreateJobForm({
                    ...createJobForm,
                    metadata: { ...createJobForm.metadata, add_frag_desc: e.target.value }
                  })}
                />
              </div>
            </div>

            <div className="flex justify-end space-x-2">
              <Button variant="outline" onClick={() => setShowUploadDialog(false)}>
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

      {/* 旧方案碎片API已删除，请使用新的异步任务API */}
    </div>
  )
}
