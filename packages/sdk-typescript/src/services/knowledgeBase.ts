/**
 * 知识库管理服务
 */

import type { 
  KBJobCreate, 
  KBJobResponse, 
  KBJobStatus 
} from '../types';

export class KnowledgeBaseService {
  private client: any; // KnowhereClient

  constructor(client: any) {
    this.client = client;
  }

  /**
   * 创建知识库管理任务
   */
  async createJob(params: KBJobCreate): Promise<KBJobResponse> {
    const response = await this.client.request('/v1/kb/jobs', {
      method: 'POST',
      body: JSON.stringify(params),
    });

    return response.data;
  }

  /**
   * 获取任务状态
   */
  async getJobStatus(jobId: string): Promise<KBJobStatus> {
    const response = await this.client.request(`/v1/kb/jobs/${jobId}`);
    return response.data;
  }

  /**
   * 下载处理结果
   */
  async downloadResult(jobId: string): Promise<any> {
    const response = await this.client.request(`/v1/kb/jobs/${jobId}/download`);
    return response.data;
  }

  /**
   * 等待任务完成
   */
  async waitForCompletion(
    jobId: string,
    timeout: number = 3600,
    pollInterval: number = 5000
  ): Promise<KBJobStatus> {
    const startTime = Date.now();

    while (Date.now() - startTime < timeout * 1000) {
      const status = await this.getJobStatus(jobId);

      if (['completed', 'failed'].includes(status.status)) {
        return status;
      }

      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }

    throw new Error(`任务 ${jobId} 在 ${timeout} 秒内未完成`);
  }
}
