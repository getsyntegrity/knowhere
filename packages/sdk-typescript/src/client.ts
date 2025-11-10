/**
 * Knowhere HTTP 客户端
 */

import type { KnowhereClientConfig, ApiResponse, ApiError } from './types';
import { KnowledgeBaseService } from './services/knowledgeBase';
import { WebhookService } from './services/webhook';
import { JobManagementService } from './services/jobManagement';

export class KnowhereClient {
  private config: Required<KnowhereClientConfig>;

  // 服务模块
  public readonly kb: KnowledgeBaseService;
  public readonly webhook: WebhookService;
  public readonly jobs: JobManagementService;

  constructor(config: KnowhereClientConfig) {
    this.config = {
      baseUrl: config.baseUrl.replace(/\/$/, ''), // 移除末尾的斜杠
      apiKey: config.apiKey || '',
      timeout: config.timeout || 30000,
      headers: {
        'Content-Type': 'application/json',
        ...config.headers,
      },
    };

    // 如果有 API Key，添加到请求头
    if (this.config.apiKey) {
      this.config.headers['Authorization'] = `Bearer ${this.config.apiKey}`;
    }

    // 初始化服务模块
    this.kb = new KnowledgeBaseService(this);
    this.webhook = new WebhookService(this);
    this.jobs = new JobManagementService(this);
  }

  /**
   * 发送 HTTP 请求
   */
  async request<T = any>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const url = `${this.config.baseUrl}${endpoint}`;
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.config.timeout);

    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          ...this.config.headers,
          ...options.headers,
        },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      const data = await response.json().catch(() => null) as T;

      if (!response.ok) {
        const error: ApiError = new Error(`HTTP ${response.status}: ${response.statusText}`);
        error.status = response.status;
        error.statusText = response.statusText;
        error.data = data;
        throw error;
      }

      return {
        data,
        status: response.status,
        statusText: response.statusText,
        headers: Object.fromEntries(response.headers.entries()),
      };
    } catch (error) {
      clearTimeout(timeoutId);
      
      if (error instanceof Error && error.name === 'AbortError') {
        const timeoutError: ApiError = new Error('Request timeout');
        timeoutError.status = 408;
        throw timeoutError;
      }
      
      throw error;
    }
  }

  /**
   * GET 请求
   */
  async get<T = any>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'GET' });
  }

  /**
   * POST 请求
   */
  async post<T = any>(endpoint: string, data?: any, options?: RequestInit): Promise<ApiResponse<T>> {
    let body: string | FormData | undefined;
    
    if (data) {
      if (data instanceof FormData) {
        body = data;
      } else {
        body = JSON.stringify(data);
      }
    }
    
    return this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      body,
    });
  }

  /**
   * PUT 请求
   */
  async put<T = any>(endpoint: string, data?: any, options?: RequestInit): Promise<ApiResponse<T>> {
    let body: string | FormData | undefined;
    
    if (data) {
      if (data instanceof FormData) {
        body = data;
      } else {
        body = JSON.stringify(data);
      }
    }
    
    return this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body,
    });
  }

  /**
   * DELETE 请求
   */
  async delete<T = any>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' });
  }

  /**
   * PATCH 请求
   */
  async patch<T = any>(endpoint: string, data?: any, options?: RequestInit): Promise<ApiResponse<T>> {
    let body: string | FormData | undefined;
    
    if (data) {
      if (data instanceof FormData) {
        body = data;
      } else {
        body = JSON.stringify(data);
      }
    }
    
    return this.request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body,
    });
  }
}
