"use client"

import { useState, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { 
  Upload, 
  CheckCircle, 
  XCircle, 
  Clock, 
  AlertCircle,
  FileText,
  RefreshCw
} from 'lucide-react'
import { api, JobCreate, JobResponse } from '@/lib/api'
import { useToast } from '@/hooks/useToast'

interface FileUploadFlowProps {
  file: File
  dataId?: string
  webhook?: {
    url: string
    secret: string
  }
  resultMode?: 'auto' | 'inline' | 'url'
  onSuccess: (job: JobResponse) => void
  onError: (error: string) => void
  onCancel?: () => void
}

type UploadStep = 'idle' | 'creating' | 'uploading' | 'confirming' | 'success' | 'error'

export default function FileUploadFlow({
  file,
  dataId,
  webhook,
  resultMode = 'auto',
  onSuccess,
  onError,
  onCancel
}: FileUploadFlowProps) {
  const toast = useToast()
  const [step, setStep] = useState<UploadStep>('idle')
  const [progress, setProgress] = useState(0)
  const [job, setJob] = useState<JobResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)

  const handleStartUpload = useCallback(async () => {
    try {
      setStep('creating')
      setError(null)
      setRetryCount(0)

      // 创建任务
      const jobCreate: JobCreate = {
        source_type: 'file',
        file_name: file.name,
        data_id: dataId,
        webhook: webhook,
        result_mode: resultMode
      }

      const jobResponse = await api.createJob(jobCreate)
      setJob(jobResponse)

      if (jobResponse.status === 'waiting-file' && jobResponse.upload_url) {
        // 开始上传到S3
        setStep('uploading')
        setProgress(0)

        await api.uploadFileToS3(
          jobResponse.upload_url,
          file,
          jobResponse.upload_headers || {},
          (progress) => {
            setProgress(progress)
          }
        )

        // 上传完成，等待5秒后进行确认
        setStep('confirming')
        
        // 等待5秒让S3事件有机会触发
        await new Promise(resolve => setTimeout(resolve, 5000))
        
        try {
          // 调用确认上传API
          console.log('开始调用confirm-upload API，job_id:', jobResponse.job_id)
          await api.confirmUpload(jobResponse.job_id)
          console.log('confirm-upload API调用成功')
          
          // 获取更新后的任务状态
          const confirmedJob = await api.getJobStatus(jobResponse.job_id)
          setJob(confirmedJob)
          
          if (confirmedJob.status === 'pending' || confirmedJob.status === 'running') {
            setStep('success')
            onSuccess(confirmedJob)
          } else {
            setError(`任务状态异常: ${confirmedJob.status}`)
            setStep('error')
            onError(`任务状态异常: ${confirmedJob.status}`)
          }
        } catch (confirmError) {
          console.error('Confirm upload failed:', confirmError)
          setError('上传确认失败，请稍后检查任务状态')
          setStep('error')
          onError('上传确认失败')
        }
      } else {
        // 直接处理（URL模式）
        setStep('success')
        onSuccess(jobResponse)
      }
    } catch (err) {
      console.error('Upload failed:', err)
      const errorMessage = err instanceof Error ? err.message : '上传失败'
      setError(errorMessage)
      setStep('error')
      onError(errorMessage)
    }
  }, [file, dataId, webhook, resultMode, onSuccess, onError])

  const handleRetry = useCallback(() => {
    if (retryCount < 3) {
      setRetryCount(prev => prev + 1)
      setError(null)
      setStep('idle')
    } else {
      toast.error('重试次数过多，请检查网络连接或联系支持')
    }
  }, [retryCount, toast])

  const getStepIcon = () => {
    switch (step) {
      case 'idle':
        return <Upload className="h-8 w-8 text-blue-500" />
      case 'creating':
        return <RefreshCw className="h-8 w-8 text-blue-500 animate-spin" />
      case 'uploading':
        return <Upload className="h-8 w-8 text-blue-500" />
      case 'confirming':
        return <Clock className="h-8 w-8 text-orange-500" />
      case 'success':
        return <CheckCircle className="h-8 w-8 text-green-500" />
      case 'error':
        return <XCircle className="h-8 w-8 text-red-500" />
      default:
        return <AlertCircle className="h-8 w-8 text-gray-500" />
    }
  }

  const getStepText = () => {
    switch (step) {
      case 'idle':
        return '准备上传'
      case 'creating':
        return '创建任务中...'
      case 'uploading':
        return `上传中... ${progress}%`
      case 'confirming':
        return '确认上传完成...'
      case 'success':
        return '上传成功'
      case 'error':
        return '上传失败'
      default:
        return '未知状态'
    }
  }

  const getStepDescription = () => {
    switch (step) {
      case 'idle':
        return '点击开始上传文件'
      case 'creating':
        return '正在创建任务并获取上传链接'
      case 'uploading':
        return '正在将文件上传到云端存储'
      case 'confirming':
        return '正在确认上传完成，准备开始处理'
      case 'success':
        return job ? `任务 ${job.job_id} 已创建，正在处理中` : '任务创建成功'
      case 'error':
        return error || '上传过程中发生错误'
      default:
        return ''
    }
  }

  return (
    <Card className="w-full max-w-md mx-auto">
      <CardContent className="p-6 space-y-4">
        {/* 文件信息 */}
        <div className="flex items-center space-x-3">
          <FileText className="h-10 w-10 text-blue-500" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate">
              {file.name}
            </p>
            <p className="text-sm text-gray-500">
              {(file.size / 1024 / 1024).toFixed(2)} MB
            </p>
          </div>
        </div>

        {/* 步骤指示器 */}
        <div className="flex items-center space-x-3">
          {getStepIcon()}
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">{getStepText()}</p>
              {step === 'success' && job && (
                <Badge variant="outline" className="text-green-600 border-green-600">
                  {job.status}
                </Badge>
              )}
            </div>
            <p className="text-xs text-gray-500 mt-1">
              {getStepDescription()}
            </p>
          </div>
        </div>

        {/* 进度条 */}
        {(step === 'uploading' || step === 'confirming') && (
          <div className="space-y-2">
            <Progress value={step === 'uploading' ? progress : 100} className="h-2" />
            {step === 'uploading' && (
              <p className="text-xs text-center text-gray-500">
                {progress}% 完成
              </p>
            )}
          </div>
        )}

        {/* 错误信息 */}
        {step === 'error' && error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* 操作按钮 */}
        <div className="flex space-x-2">
          {step === 'idle' && (
            <Button onClick={handleStartUpload} className="flex-1">
              <Upload className="mr-2 h-4 w-4" />
              开始上传
            </Button>
          )}
          
          {step === 'error' && retryCount < 3 && (
            <Button onClick={handleRetry} variant="outline" className="flex-1">
              <RefreshCw className="mr-2 h-4 w-4" />
              重试 ({retryCount}/3)
            </Button>
          )}
          
          {onCancel && step !== 'success' && (
            <Button onClick={onCancel} variant="outline">
              取消
            </Button>
          )}
        </div>

        {/* 成功后的任务信息 */}
        {step === 'success' && job && (
          <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-md">
            <p className="text-sm text-green-800">
              <strong>任务ID:</strong> {job.job_id}
            </p>
            <p className="text-sm text-green-800">
              <strong>状态:</strong> {job.status}
            </p>
            <p className="text-xs text-green-600 mt-1">
              您可以在任务管理页面查看处理进度
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
