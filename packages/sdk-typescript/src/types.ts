/**
 * 类型定义
 */

export interface KnowhereClientConfig {
  apiKey: string;
  baseUrl?: string;
  timeout?: number;
  headers?: Record<string, string>;
}

export interface ApiResponse<T = any> {
  success: boolean;
  data: T;
  error?: {
    code: string;
    message: string;
    details?: any;
  };
}

export class ApiError extends Error {
  public code?: string;
  public details?: any;

  constructor(message: string, code?: string, details?: any) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.details = details;
  }
}

// 表格填充相关类型
export interface TableFillJobCreate {
  fileUrl: string;
  webhookUrl?: string;
  metadata?: Record<string, any>;
}

export interface TableFillJobResponse {
  jobId: string;
  status: string;
  currentState: string;
  createdAt: string;
  fileUrl: string;
  webhookUrl?: string;
}

export interface TableFillJobStatus {
  jobId: string;
  status: string;
  currentState: string;
  progress?: number;
  createdAt: string;
  updatedAt: string;
  fileUrl: string;
  webhookUrl?: string;
  metadata?: Record<string, any>;
  errorMessage?: string;
}

// 知识库相关类型
export interface KBJobCreate {
  fileUrl: string;
  webhookUrl?: string;
  metadata?: Record<string, any>;
}

export interface KBJobResponse {
  jobId: string;
  status: string;
  currentState: string;
  createdAt: string;
  fileUrl: string;
  webhookUrl?: string;
}

export interface KBJobStatus {
  jobId: string;
  status: string;
  currentState: string;
  progress?: number;
  createdAt: string;
  updatedAt: string;
  fileUrl: string;
  webhookUrl?: string;
  metadata?: Record<string, any>;
  processingStats?: Record<string, any>;
  errorMessage?: string;
}

// Webhook相关类型
export interface WebhookConfig {
  webhookId: string;
  webhookUrl: string;
  events: string[];
  secret?: string;
  createdAt: string;
  updatedAt: string;
}

export interface WebhookLogResponse {
  logId: string;
  jobId: string;
  eventType: string;
  webhookUrl: string;
  statusCode?: number;
  responseBody?: string;
  retryCount: number;
  createdAt: string;
  lastAttemptAt: string;
}

// 任务管理相关类型
export interface JobStatusResponse {
  jobId: string;
  jobType: string;
  status: string;
  currentState: string;
  progress?: number;
  createdAt: string;
  updatedAt: string;
  fileUrl: string;
  webhookUrl?: string;
  metadata?: Record<string, any>;
  errorMessage?: string;
}

export interface JobResultResponse {
  jobId: string;
  jobType: string;
  status: string;
  resultS3Key?: string;
  downloadUrl?: string;
  processingStats?: Record<string, any>;
  createdAt: string;
  completedAt?: string;
}