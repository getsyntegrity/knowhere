/**
 * 任务管理服务
 */

import type { 
  JobStatusResponse, 
  JobResultResponse 
} from '../types';

export class JobManagementService {
  private client: any; // KnowhereClient

  constructor(client: any) {
    this.client = client;
  }

  /**
   * 获取任务状态
   */
  async getJobStatus(jobId: string): Promise<JobStatusResponse> {
    const response = await this.client.request(`/v1/jobs/${jobId}/status`);
    return response.data;
  }

  /**
   * 获取任务结果
   */
  async getJobResult(jobId: string): Promise<JobResultResponse> {
    const response = await this.client.request(`/v1/jobs/${jobId}/result`);
    return response.data;
  }

  /**
   * 取消任务
   */
  async cancelJob(jobId: string): Promise<boolean> {
    try {
      await this.client.request(`/v1/jobs/${jobId}/cancel`, {
        method: 'POST',
      });
      return true;
    } catch (error) {
      return false;
    }
  }

  /**
   * 获取用户的所有任务
   */
  async getUserJobs(params?: {
    jobType?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<JobStatusResponse[]> {
    const queryParams = new URLSearchParams();
    if (params?.jobType) queryParams.append('job_type', params.jobType);
    if (params?.status) queryParams.append('status', params.status);
    if (params?.limit) queryParams.append('limit', params.limit.toString());
    if (params?.offset) queryParams.append('offset', params.offset.toString());

    const response = await this.client.request(`/v1/jobs?${queryParams}`);
    return response.data;
  }
}
