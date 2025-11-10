"""
邮件服务
"""
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger

from app.core.config import settings


class EmailService:
    """邮件服务"""
    
    def __init__(self):
        self.resend_api_key = settings.RESEND_API_KEY
        self.base_url = "https://api.resend.com"
        self.from_email = "noreply@knowhere.ai"
        self.from_name = "Knowhere AI"
    
    async def send_email(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        发送邮件
        
        Args:
            to: 收件人邮箱
            subject: 邮件主题
            html_content: HTML内容
            text_content: 纯文本内容（可选）
            
        Returns:
            Dict: 发送结果
        """
        try:
            if not self.resend_api_key:
                logger.warning("Resend API Key未配置，跳过邮件发送")
                return {"success": False, "error": "API Key未配置"}
            
            headers = {
                "Authorization": f"Bearer {self.resend_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [to],
                "subject": subject,
                "html": html_content
            }
            
            if text_content:
                payload["text"] = text_content
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/emails",
                    json=payload,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"邮件发送成功: {to}")
                        return {"success": True, "id": result.get("id")}
                    else:
                        error_text = await response.text()
                        logger.error(f"邮件发送失败: {response.status} - {error_text}")
                        return {"success": False, "error": error_text}
                        
        except Exception as e:
            logger.error(f"邮件发送异常: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_welcome_email(self, user_email: str, user_name: str = None) -> Dict[str, Any]:
        """发送欢迎邮件"""
        try:
            subject = "欢迎使用 Knowhere AI！"
            html_content = self._get_welcome_email_html(user_name or user_email)
            text_content = self._get_welcome_email_text(user_name or user_email)
            
            return await self.send_email(
                to=user_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content
            )
            
        except Exception as e:
            logger.error(f"发送欢迎邮件失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_purchase_confirmation_email(
        self, 
        user_email: str, 
        plan_type: str, 
        amount: float,
        user_name: str = None
    ) -> Dict[str, Any]:
        """发送购买确认邮件"""
        try:
            subject = f"购买确认 - {plan_type.title()} 订阅"
            html_content = self._get_purchase_confirmation_html(
                user_name or user_email, plan_type, amount
            )
            text_content = self._get_purchase_confirmation_text(
                user_name or user_email, plan_type, amount
            )
            
            return await self.send_email(
                to=user_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content
            )
            
        except Exception as e:
            logger.error(f"发送购买确认邮件失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_job_completion_email(
        self,
        user_email: str,
        job_type: str,
        job_id: str,
        download_url: str = None,
        user_name: str = None
    ) -> Dict[str, Any]:
        """发送任务完成邮件"""
        try:
            subject = f"任务完成 - {job_type.replace('_', ' ').title()}"
            html_content = self._get_job_completion_html(
                user_name or user_email, job_type, job_id, download_url
            )
            text_content = self._get_job_completion_text(
                user_name or user_email, job_type, job_id, download_url
            )
            
            return await self.send_email(
                to=user_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content
            )
            
        except Exception as e:
            logger.error(f"发送任务完成邮件失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_welcome_email_html(self, user_name: str) -> str:
        """获取欢迎邮件HTML模板"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>欢迎使用 Knowhere AI</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .button {{ display: inline-block; background: #667eea; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 欢迎使用 Knowhere AI！</h1>
                </div>
                <div class="content">
                    <h2>你好，{user_name}！</h2>
                    <p>感谢您注册 Knowhere AI 知识库管理系统！我们很高兴您加入我们的社区。</p>
                    
                    <h3>🚀 开始使用</h3>
                    <p>作为新用户，您已自动获得：</p>
                    <ul>
                        <li><strong>Free 订阅计划</strong> - 每月 100 个 Credits</li>
                        <li><strong>表格填充功能</strong> - 智能表格数据填充</li>
                        <li><strong>知识库管理</strong> - 文档解析和向量化</li>
                        <li><strong>API 访问</strong> - 完整的 REST API</li>
                    </ul>
                    
                    <div style="text-align: center;">
                        <a href="https://knowhere.ai/dashboard" class="button">进入控制台</a>
                    </div>
                    
                    <h3>📚 快速开始</h3>
                    <p>查看我们的文档了解如何：</p>
                    <ul>
                        <li>创建您的第一个知识库</li>
                        <li>使用表格填充功能</li>
                        <li>集成 API 到您的应用</li>
                    </ul>
                    
                    <p>如有任何问题，请随时联系我们的支持团队。</p>
                </div>
                <div class="footer">
                    <p>© 2024 Knowhere AI. 保留所有权利。</p>
                    <p>如果您没有注册此账户，请忽略此邮件。</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _get_welcome_email_text(self, user_name: str) -> str:
        """获取欢迎邮件纯文本模板"""
        return f"""
        欢迎使用 Knowhere AI！
        
        你好，{user_name}！
        
        感谢您注册 Knowhere AI 知识库管理系统！我们很高兴您加入我们的社区。
        
        作为新用户，您已自动获得：
        - Free 订阅计划 - 每月 100 个 Credits
        - 表格填充功能 - 智能表格数据填充
        - 知识库管理 - 文档解析和向量化
        - API 访问 - 完整的 REST API
        
        开始使用：https://knowhere.ai/dashboard
        
        快速开始：
        - 创建您的第一个知识库
        - 使用表格填充功能
        - 集成 API 到您的应用
        
        如有任何问题，请随时联系我们的支持团队。
        
        © 2024 Knowhere AI. 保留所有权利。
        """
    
    def _get_purchase_confirmation_html(self, user_name: str, plan_type: str, amount: float) -> str:
        """获取购买确认邮件HTML模板"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>购买确认</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #28a745; color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .receipt {{ background: white; padding: 20px; border-radius: 5px; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>✅ 购买确认</h1>
                </div>
                <div class="content">
                    <h2>你好，{user_name}！</h2>
                    <p>感谢您的购买！您的订阅已成功激活。</p>
                    
                    <div class="receipt">
                        <h3>购买详情</h3>
                        <p><strong>订阅计划：</strong> {plan_type.title()}</p>
                        <p><strong>金额：</strong> ${amount:.2f}</p>
                        <p><strong>购买时间：</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    </div>
                    
                    <p>您现在可以享受更高级的功能和更多的 Credits。</p>
                    
                    <div style="text-align: center;">
                        <a href="https://knowhere.ai/dashboard" style="display: inline-block; background: #28a745; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px;">进入控制台</a>
                    </div>
                </div>
                <div class="footer">
                    <p>© 2024 Knowhere AI. 保留所有权利。</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _get_purchase_confirmation_text(self, user_name: str, plan_type: str, amount: float) -> str:
        """获取购买确认邮件纯文本模板"""
        return f"""
        购买确认
        
        你好，{user_name}！
        
        感谢您的购买！您的订阅已成功激活。
        
        购买详情：
        - 订阅计划：{plan_type.title()}
        - 金额：${amount:.2f}
        - 购买时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        您现在可以享受更高级的功能和更多的 Credits。
        
        进入控制台：https://knowhere.ai/dashboard
        
        © 2024 Knowhere AI. 保留所有权利。
        """
    
    def _get_job_completion_html(self, user_name: str, job_type: str, job_id: str, download_url: str = None) -> str:
        """获取任务完成邮件HTML模板"""
        job_type_display = job_type.replace('_', ' ').title()
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>任务完成</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #17a2b8; color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .job-info {{ background: white; padding: 20px; border-radius: 5px; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 任务完成！</h1>
                </div>
                <div class="content">
                    <h2>你好，{user_name}！</h2>
                    <p>您的 {job_type_display} 任务已成功完成。</p>
                    
                    <div class="job-info">
                        <h3>任务详情</h3>
                        <p><strong>任务类型：</strong> {job_type_display}</p>
                        <p><strong>任务ID：</strong> {job_id}</p>
                        <p><strong>完成时间：</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    </div>
                    
                    {f'<div style="text-align: center;"><a href="{download_url}" style="display: inline-block; background: #17a2b8; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px;">下载结果</a></div>' if download_url else ''}
                    
                    <p>感谢您使用 Knowhere AI！</p>
                </div>
                <div class="footer">
                    <p>© 2024 Knowhere AI. 保留所有权利。</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _get_job_completion_text(self, user_name: str, job_type: str, job_id: str, download_url: str = None) -> str:
        """获取任务完成邮件纯文本模板"""
        job_type_display = job_type.replace('_', ' ').title()
        
        return f"""
        任务完成
        
        你好，{user_name}！
        
        您的 {job_type_display} 任务已成功完成。
        
        任务详情：
        - 任务类型：{job_type_display}
        - 任务ID：{job_id}
        - 完成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        {f'下载结果：{download_url}' if download_url else ''}
        
        感谢您使用 Knowhere AI！
        
        © 2024 Knowhere AI. 保留所有权利。
        """
