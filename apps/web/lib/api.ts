/**
 * API客户端 - 基于原生fetch
 * 统一处理后端API请求和响应
 */

// ============================================
// 类型定义
// ============================================


/**
 * API错误类
 */
export class ApiError extends Error {
  code: number
  status?: number
  
  constructor(message: string, code: number, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

// ============================================
// 请求相关类型
// ============================================

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  password: string
  username: string
}

export interface User {
  id: string
  email: string
  username: string
  user_type: string
  is_active: boolean
  is_verified: boolean
  credits_balance: number
  avatar_url?: string
  phone?: string
  create_time: string
}

export interface CreateAPIKeyRequest {
  name: string
  enabled_modules?: string[]
  expires_at?: string
}

export interface APIKey {
  id: string
  name: string
  enabled_modules?: string[]
  is_active: boolean
  created_at: string
  last_used_at?: string
  expires_at?: string
  api_key?: string  // 仅在创建时返回，列表时不返回
}

export interface CreateAPIKeyResponse {
  api_key: string
  name: string
  enabled_modules?: string[]
  expires_at?: string
}

export interface CreditsBalance {
  credits_balance: number
  credits_limit: number
  usage_percentage: number
}

export interface UsageStats {
  period: string
  total_credits_used: number
  api_calls_count: number
  success_rate: number
  average_response_time: number
  top_endpoints: Array<{
    endpoint: string
    calls: number
    credits_used: number
  }>
}

export interface Transaction {
  id: string
  type: 'credit' | 'debit'
  credits_amount: number
  description: string
  created_at: string
}

// ============================================
// 订阅和计费相关类型
// ============================================

export interface Subscription {
  id: string
  plan_type: 'free' | 'plus' | 'pro'
  status: 'active' | 'canceled' | 'past_due'
  start_date: string
  end_date?: string
  credits_limit: number
  stripe_subscription_id?: string
}

export interface CreditPackage {
  id: string
  amount: number
  expires_at: string
  status: 'active' | 'expired'
  purchase_date: string
}

export interface SubscriptionPlan {
  id: string
  plan_id: string
  price_id?: string
  name: string
  price?: number
  period?: string
  credits?: number
  features: string[]
  popular: boolean
  stripe_price_id?: string
  description?: string
  amount_cents?: number
  currency?: string
  metadata?: Record<string, any>
}

export interface CreditsPackage {
  id: string
  plan_id: string
  price_id: string
  name: string
  description?: string
  credits_amount: number
  amount_cents: number
  currency: string
  metadata?: Record<string, any>
}

export interface PriceConfigsResponse {
  subscriptions: SubscriptionPlan[]
  credits_packages: CreditsPackage[]
}

export interface CreditPackagePurchase {
  credits_amount: number
  amount_cny: number
  payment_method_id?: string
}

export interface CheckoutSessionResponse {
  checkout_url: string
  session_id: string
}

export interface PaymentIntentResponse {
  client_secret: string
  payment_intent_id: string
}

// ============================================
// 知识库相关类型
// ============================================

export interface KnowledgeBase {
  id: string
  content?: string
  path?: string
  type?: string
  length?: number
  keywords?: string
  summary?: string
  know_id?: string
  tokens?: string
  embedding?: string
}

export interface AddKBPathRequest {
  path: string
  label: string[]
}

// 旧方案同步API接口已删除，请使用新的异步任务API

export interface SearchAskRequest {
  question: string
  topk?: number
  filter_nodes: string[]
  filter_mode: string
  filter_type?: number
  show_image: boolean
  rerank: boolean
  ask: boolean
  ask_multimodal?: boolean
  ask_agent?: boolean
}

export interface SearchAskResponse {
  answer?: string
  context: string
  sim_contents: Array<{
    content: string
    path: string
    similarity: number
  }>
}

// ============================================
// 统一任务相关类型（符合PRD规范）
// ============================================

export interface WebhookConfig {
  url: string
  secret: string
}

export interface ParsingParams {
  model?: 'base' | 'advanced'
  ocr_enabled?: boolean
  kb_dir?: string
  doc_type?: 'auto' | 'pdf' | 'docx' | 'txt' | 'md'
  smart_title_parse?: boolean
  summary_image?: boolean
  summary_table?: boolean
  summary_txt?: boolean
  add_frag_desc?: string
}

export interface JobCreate {
  source_type: 'file' | 'url'
  source_url?: string
  file_name?: string
  data_id?: string
  parsing_params?: ParsingParams
  webhook?: WebhookConfig
  result_mode?: 'auto' | 'inline' | 'url'
}

export interface JobResponse {
  job_id: string
  status: string
  source_type: string
  data_id?: string
  created_at: string
  result_mode: 'auto' | 'inline' | 'url'
  
  // waiting-file状态特有字段
  upload_url?: string
  upload_headers?: Record<string, string>
  expires_in?: number
  
  // running状态特有字段
  progress?: Record<string, any>
  
  // done状态特有字段
  result?: Record<string, any>
  result_url?: string
  result_metadata?: Record<string, any>
  
  // failed状态特有字段
  error?: Record<string, any>
}

export interface JobStatus {
  job_id: string
  status: string
  source_type: string
  data_id?: string
  created_at: string
  updated_at?: string
  result_mode: 'auto' | 'inline' | 'url'
  
  // 状态相关字段
  current_state?: string
  progress?: Record<string, any>
  error?: Record<string, any>
  
  // 结果相关字段
  result?: Record<string, any>
  result_url?: string
  result_metadata?: Record<string, any>
  
  // 元数据
  file_path?: string
  s3_key?: string
  webhook_url?: string
  webhook_enabled: boolean
}

export interface JobList {
  jobs: JobResponse[]
  total: number
  page: number
  page_size: number
}

// ============================================
// 核心API客户端类
// ============================================

class KnowhereAPI {
  private baseUrl: string
  private token: string | null = null

  constructor() {
    this.baseUrl = process.env.NEXT_PUBLIC_API_URL || '/api'
    // 初始化时从localStorage读取token（仅在浏览器环境）
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('auth_token')
    }
  }

  /**
   * 更新token
   */
  updateToken(token: string | null) {
    this.token = token
    if (typeof window !== 'undefined') {
      if (token) {
        localStorage.setItem('auth_token', token)
      } else {
        localStorage.removeItem('auth_token')
      }
    }
  }

  /**
   * 验证token格式
   */
  private isValidToken(token: string): boolean {
    if (!token || typeof token !== 'string') {
      return false
    }
    
    // JWT token通常包含三个部分，用.分隔
    const parts = token.split('.')
    if (parts.length !== 3) {
      return false
    }
    
    // 检查每个部分是否都是有效的base64
    try {
      parts.forEach(part => {
        if (part.length === 0) throw new Error('Empty part')
        // 简单的base64检查
        atob(part.replace(/-/g, '+').replace(/_/g, '/'))
      })
      return true
    } catch {
      return false
    }
  }

  /**
   * 统一的fetch请求封装
   */
  private async request<T = any>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`
    
    // 构建请求头
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    }
    
    // 只有在没有设置Content-Type且不是FormData时才设置默认的Content-Type
    if (!headers['Content-Type'] && !(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json'
    }

    // 添加Authorization header（如果有token）
    if (this.token) {
      // 验证token格式
      if (!this.isValidToken(this.token)) {
        console.warn('Invalid token format, clearing token')
        this.updateToken(null)
        throw new ApiError('Token格式无效，请重新登录', 401)
      }
      headers['Authorization'] = `Bearer ${this.token}`
    }

    // 发送请求
    try {
      const response = await fetch(url, {
        ...options,
        headers,
        cache: options.cache || 'no-store', // 默认不缓存
      })

      // 解析响应
      const result = await response.json()

      // 检查HTTP状态码
      if (!response.ok) {
        // 如果是401错误，清除本地token
        if (response.status === 401) {
          console.warn('收到401响应，清除本地token')
          this.updateToken(null)
        }
        
        throw new ApiError(
          result.detail || result.msg || `HTTP错误: ${response.status}`,
          result.code || response.status,
          response.status
        )
      }

      // 直接返回结果，不再检查ResponseResult格式
      return result
    } catch (error) {
      // 网络错误或其他异常
      if (error instanceof ApiError) {
        throw error
      }
      
      if (error instanceof Error) {
        throw new ApiError(error.message, 500)
      }
      
      throw new ApiError('未知错误', 500)
    }
  }

  /**
   * GET请求
   */
  private async get<T = any>(
    endpoint: string,
    options?: RequestInit
  ): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET' })
  }

  /**
   * POST请求
   */
  private async post<T = any>(
    endpoint: string,
    data?: any,
    options?: RequestInit
  ): Promise<T> {
    const isFormData = data instanceof FormData
    
    return this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      headers: isFormData ? options?.headers : { 'Content-Type': 'application/json', ...options?.headers },
      body: isFormData ? data : JSON.stringify(data),
    })
  }

  /**
   * PUT请求
   */
  private async put<T = any>(
    endpoint: string,
    data?: any,
    options?: RequestInit
  ): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: JSON.stringify(data),
    })
  }

  /**
   * DELETE请求
   */
  private async delete<T = any>(
    endpoint: string,
    options?: RequestInit
  ): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' })
  }

  /**
   * PATCH请求
   */
  private async patch<T = any>(
    endpoint: string,
    data?: any,
    options?: RequestInit
  ): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  // ============================================
  // 认证相关API
  // ============================================

  /**
   * 登录
   */
  async login(credentials: LoginRequest) {
    // 使用URLSearchParams创建application/x-www-form-urlencoded格式
    const formData = new URLSearchParams()
    formData.append('username', credentials.email)
    formData.append('password', credentials.password)

    return this.request<{ access_token: string; token_type: string }>(
      '/v1/jwt/login',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData.toString(),
      }
    )
  }

  /**
   * 注册
   */
  async register(userData: RegisterRequest) {
    return this.post<User>('/v1/register', userData)
  }

  /**
   * 获取当前用户信息
   */
  async getCurrentUser() {
    return this.get<User>('/v1/me')
  }

  /**
   * OAuth登录
   */
  async oauthLogin(provider: 'google' | 'apple' | 'github', token: string) {
    const payload = provider === 'github' 
      ? { code: token }
      : { id_token: token }
    
    return this.post<{ access_token: string; user_info?: User }>(
      `/v1/auth/oauth/${provider}`,
      payload
    )
  }

  /**
   * 续期访问令牌
   */
  async renewToken() {
    return this.post<{ access_token: string; token_type: string }>('/v1/renew-token')
  }

  /**
   * 登出
   */
  async logout() {
    return this.post('/v1/jwt/logout')
  }

  // ============================================
  // API Key管理API
  // ============================================

  /**
   * 获取API Key列表
   */
  async listApiKeys() {
    return this.get<{ api_keys: APIKey[] }>('/v1/auth/list')
  }

  /**
   * 创建API Key
   */
  async createApiKey(data: CreateAPIKeyRequest) {
    return this.post<CreateAPIKeyResponse>('/v1/auth/create', data)
  }

  /**
   * 重新生成API Key
   */
  async regenerateApiKey(apiKeyId: string) {
    return this.post<{ api_key: string }>('/v1/auth/regenerate', {
      api_key_id: apiKeyId,
    })
  }

  /**
   * 撤销API Key
   */
  async revokeApiKey(apiKeyId: string) {
    return this.post('/v1/auth/revoke', { api_key_id: apiKeyId })
  }

  /**
   * 切换API Key状态
   */
  async toggleApiKey(apiKeyId: string) {
    return this.put(`/v1/auth/${apiKeyId}/toggle`)
  }

  /**
   * 获取单个API Key详情
   */
  async getApiKey(apiKeyId: string) {
    return this.get<APIKey>(`/v1/auth/${apiKeyId}`)
  }

  // ============================================
  // 用户管理API
  // ============================================

  /**
   * 获取用户资料
   */
  async getUserProfile() {
    return this.get<User>('/v1/user/profile')
  }

  /**
   * 更新用户资料
   */
  async updateUserProfile(data: Partial<User>) {
    return this.put<User>('/v1/user/profile', data)
  }

  // ============================================
  // 计费管理API
  // ============================================

  /**
   * 获取Credits余额
   */
  async getCreditsBalance() {
    return this.get<CreditsBalance>('/v1/billing/credits')
  }

  /**
   * 购买Credits
   */
  async buyCredits(amount: number) {
    return this.post<PaymentIntentResponse>('/v1/billing/buy-credits', {
      credits_amount: amount,
    })
  }

  /**
   * 订阅计划
   */
  async subscribePlan(planId: string) {
    return this.post<CheckoutSessionResponse>('/v1/billing/subscribe', {
      plan_id: planId,
    })
  }

  /**
   * 获取当前订阅信息
   */
  async getCurrentSubscription() {
    return this.get<Subscription>('/v1/billing/subscription')
  }

  /**
   * 获取价格配置列表
   */
  async getPriceConfigs(productType?: 'subscription' | 'credits_package') {
    const params = productType ? `?product_type=${productType}` : ''
    return this.get<PriceConfigsResponse>(`/v1/billing/price-configs${params}`)
  }

  /**
   * 通过价格ID购买Credits包
   */
  async buyCreditsPackage(priceId: string) {
    return this.post<CheckoutSessionResponse>('/v1/billing/buy-credits-package', {
      price_id: priceId,
    })
  }

  /**
   * 取消订阅
   */
  async cancelSubscription() {
    return this.post('/v1/billing/cancel-subscription')
  }

  /**
   * 获取Credits量包列表
   */
  async getCreditPackages() {
    return this.get<CreditPackage[]>('/v1/billing/credit-packages')
  }

  /**
   * 获取使用统计
   */
  async getUsageStats(period: string = 'month') {
    return this.get<UsageStats>(`/v1/billing/usage?period=${period}`)
  }

  /**
   * 获取交易历史
   */
  async getTransactionHistory(limit: number = 50, offset: number = 0) {
    return this.get<{ transactions: Transaction[]; total: number }>(
      `/v1/user/credits/transactions?limit=${limit}&offset=${offset}`
    )
  }


  // ============================================
  // 知识库管理API
  // ============================================

  /**
   * 添加知识库路径
   */
  async addKBPath(data: AddKBPathRequest) {
    return this.post('/v1/kb/add_kb', data)
  }

  // ============================================
  // 统一任务API
  // ============================================

  /**
   * 创建任务
   */
  async createJob(data: JobCreate) {
    return this.post<JobResponse>('/v1/jobs', data)
  }

  /**
   * 获取任务状态
   */
  async getJobStatus(jobId: string) {
    return this.get<JobStatus>(`/v1/jobs/${jobId}`)
  }

  /**
   * 获取任务列表
   */
  async listJobs(params?: { 
    page?: number; 
    page_size?: number; 
    status?: string;
    job_type?: string;
  }) {
    const queryParams = new URLSearchParams()
    if (params?.page) queryParams.append('page', params.page.toString())
    if (params?.page_size) queryParams.append('page_size', params.page_size.toString())
    if (params?.status) queryParams.append('status', params.status)
    if (params?.job_type) queryParams.append('job_type', params.job_type)
    
    const query = queryParams.toString()
    return this.get<JobList>(`/v1/jobs/page${query ? `?${query}` : ''}`)
  }

  /**
   * 确认文件上传完成（备用机制）
   */
  async confirmUpload(jobId: string) {
    return this.post(`/v1/jobs/${jobId}/confirm-upload`)
  }

  /**
   * 直接上传文件到S3预签名URL
   */
  async uploadFileToS3(
    uploadUrl: string, 
    file: File, 
    headers: Record<string, string>,
    onProgress?: (progress: number) => void
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      
      // 监听上传进度
      if (onProgress) {
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable) {
            const progress = Math.round((event.loaded / event.total) * 100)
            onProgress(progress)
          }
        })
      }
      
      // 监听完成事件
      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve()
        } else {
          reject(new Error(`Upload failed with status ${xhr.status}`))
        }
      })
      
      // 监听错误事件
      xhr.addEventListener('error', () => {
        reject(new Error('Upload failed due to network error'))
      })
      
      // 监听超时事件
      xhr.addEventListener('timeout', () => {
        reject(new Error('Upload timed out'))
      })
      
      // 设置超时时间（5分钟）
      xhr.timeout = 5 * 60 * 1000
      
      // 开始上传
      xhr.open('PUT', uploadUrl)
      
      // 设置请求头
      Object.entries(headers).forEach(([key, value]) => {
        xhr.setRequestHeader(key, value)
      })
      
      xhr.send(file)
    })
  }

  // ============================================
  // 保留的搜索API（暂时保留，后续可能迁移到异步）
  // ============================================

  /**
   * 搜索知识库
   */
  async searchKB(data: SearchAskRequest) {
    return this.post<SearchAskResponse>('/v1/kb/search', data)
  }

  /**
   * 获取知识库文件树
   */
  async getFileTree(kb_path: string) {
    return this.post('/v1/kb/get_fileTree', {
      kb_path
    })
  }

  /**
   * 获取用户目录列表
   */
  async getDirectories() {
    return this.post('/v1/kb/get_directory')
  }

  /**
   * 获取目录下的知识库内容
   */
  async getDirectoryContents(directoryId: string) {
    return this.post('/v1/kb/list_directory', {
      id: directoryId
    })
  }

  /**
   * 删除知识库内容
   */
  async deleteKBContent(contentId: string) {
    return this.delete(`/v1/kb/contents/${contentId}`)
  }

  // ============================================
}

// 导出单例实例
export const api = new KnowhereAPI()
