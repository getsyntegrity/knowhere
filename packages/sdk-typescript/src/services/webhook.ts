/**
 * Webhook服务
 */

import type { 
  WebhookConfig, 
  WebhookLogResponse 
} from '../types';

export class WebhookService {
  private client: any; // KnowhereClient

  constructor(client: any) {
    this.client = client;
  }

  /**
   * 创建Webhook配置
   */
  async createConfig(params: {
    webhookUrl: string;
    events?: string[];
    secret?: string;
  }): Promise<WebhookConfig> {
    const response = await this.client.request('/v1/webhooks/config', {
      method: 'POST',
      body: JSON.stringify(params),
    });

    return response.data;
  }

  /**
   * 获取Webhook配置
   */
  async getConfig(): Promise<WebhookConfig | null> {
    try {
      const response = await this.client.request('/v1/webhooks/config');
      return response.data;
    } catch (error) {
      return null;
    }
  }

  /**
   * 更新Webhook配置
   */
  async updateConfig(params: {
    webhookUrl?: string;
    events?: string[];
    secret?: string;
  }): Promise<WebhookConfig> {
    const response = await this.client.request('/v1/webhooks/config', {
      method: 'PUT',
      body: JSON.stringify(params),
    });

    return response.data;
  }

  /**
   * 删除Webhook配置
   */
  async deleteConfig(): Promise<boolean> {
    try {
      await this.client.request('/v1/webhooks/config', {
        method: 'DELETE',
      });
      return true;
    } catch (error) {
      return false;
    }
  }

  /**
   * 获取Webhook日志
   */
  async getLogs(params?: {
    jobId?: string;
    limit?: number;
    offset?: number;
  }): Promise<WebhookLogResponse[]> {
    const queryParams = new URLSearchParams();
    if (params?.jobId) queryParams.append('job_id', params.jobId);
    if (params?.limit) queryParams.append('limit', params.limit.toString());
    if (params?.offset) queryParams.append('offset', params.offset.toString());

    const response = await this.client.request(`/v1/webhooks/logs?${queryParams}`);
    return response.data;
  }
}
