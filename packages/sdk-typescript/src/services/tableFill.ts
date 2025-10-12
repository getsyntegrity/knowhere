/**
 * 表格填充服务
 */

import type { 
  TableFillJobCreate, 
  TableFillJobResponse, 
  TableFillJobStatus 
} from '../types';

export class TableFillService {
  private client: any; // KnowhereClient

  constructor(client: any) {
    this.client = client;
  }

  /**
   * 创建表格填充任务
   */
  async createJob(params: TableFillJobCreate): Promise<TableFillJobResponse> {
    const response = await this.client.request('/v1/table-fill/jobs', {
      method: 'POST',
      body: JSON.stringify(params),
    });

    return response.data;
  }

  /**
   * 获取任务状态
   */
  async getJobStatus(jobId: string): Promise<TableFillJobStatus> {
    const response = await this.client.request(`/v1/table-fill/jobs/${jobId}`);
    return response.data;
  }

  /**
   * 下载结果文件
   */
  async downloadResult(jobId: string): Promise<Blob> {
    const response = await fetch(`${this.client.config.baseUrl}/v1/table-fill/jobs/${jobId}/download`, {
      headers: {
        'Authorization': `Bearer ${this.client.config.apiKey}`,
      },
    });

    if (!response.ok) {
      throw new Error(`下载失败: ${response.statusText}`);
    }

    return response.blob();
  }

  /**
   * 等待任务完成
   */
  async waitForCompletion(
    jobId: string,
    timeout: number = 3600,
    pollInterval: number = 5000
  ): Promise<TableFillJobStatus> {
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
