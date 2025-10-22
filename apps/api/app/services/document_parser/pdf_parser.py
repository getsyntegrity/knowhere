import os
import requests
from app.services.document_parser.md_parser import parse_md
from app.utils.FileDownUpUtils import s3_download_extract_zip
from app.core.config import settings
from loguru import logger


async def parse_pdfs(pdf_path, filename, output_dir, base_llm_paras, mode="api"):
    if mode == "api":
        url = settings.MINERU_URL
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.MINERU_API_KEY}",
        }
        data = {
            "url": pdf_path,
            "is_ocr": True,
            "enable_formula": True,
            "language": "auto"
        }
        logger.debug(f"parse_pdfs data: {data}")
        logger.debug(f"parse_pdfs url: {url}")
        logger.debug(f"parse_pdfs header: {header}")
        res = requests.post(url, headers=header, json=data)
        logger.debug(f"parse_pdfs res: {res.json()}")
        
        if res.status_code == 200:
            sent_info = (res.json())["data"]
            status_url = f"https://mineru.net/api/v4/extract/task/{sent_info['task_id']}"
            status_header = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.MINERU_API_KEY}"
            }

            # 优化轮询策略：添加延迟、超时和错误处理
            import time
            import asyncio
            
            max_polling_attempts = 120   # 最大轮询次数 (10分钟)
            polling_interval = 5.0      # 轮询间隔(秒)
            max_wait_time = 600         # 最大等待时间(10分钟)
            
            # 动态轮询间隔：根据任务状态调整
            def get_polling_interval(state: str, attempt: int) -> float:
                if state == "pending":
                    return min(10.0, 2.0 + attempt * 0.5)  # 等待中逐渐增加间隔
                elif state == "running":
                    return 5.0  # 运行中保持5秒间隔
                else:
                    return 2.0  # 其他状态快速检查
            
            start_time = time.time()
            attempt = 0
            
            while attempt < max_polling_attempts:
                # 检查是否超时
                if time.time() - start_time > max_wait_time:
                    raise TimeoutError(f"PDF解析超时，等待时间超过{max_wait_time}秒")
                
                try:
                    logger.debug(f"parse_pdfs status_url: {status_url} (尝试 {attempt + 1}/{max_polling_attempts})")
                    res = requests.get(status_url, headers=status_header, timeout=30)
                    
                    if res.status_code == 200:
                        status = res.json()["data"]
                        logger.debug(f"parse_pdfs status_res: {status}")
                        
                        if status['state'] == "done":
                            # 解析完成
                            res_zip_url = status['full_zip_url']
                            s3_download_extract_zip(res_zip_url, dest_dir=output_dir, 
                                                  keep_exts=['.md', '.jpg', '.jpeg', '.png', '.gif'])
                            logger.info(f"PDF解析完成，任务ID: {sent_info['task_id']}")
                            break
                            
                        elif status['state'] == "running":
                            # 显示进度
                            if 'extract_progress' in status:
                                progress = (status['extract_progress']['extracted_pages'] / 
                                          status['extract_progress']['total_pages'])
                                logger.info(f"PDF解析进度: {progress:.2%} (任务ID: {sent_info['task_id']})")
                            else:
                                logger.info(f"PDF解析进行中... (任务ID: {sent_info['task_id']})")
                            
                        elif status['state'] == "failed":
                            # 解析失败
                            error_msg = status.get('err_msg', '未知错误')
                            raise Exception(f"PDF解析失败: {error_msg}")
                        
                        elif status['state'] == "pending":
                            # 等待中
                            logger.info(f"PDF解析等待中... (任务ID: {sent_info['task_id']})")
                        
                        # 动态调整轮询间隔
                        current_interval = get_polling_interval(status['state'], attempt)
                        await asyncio.sleep(current_interval)
                        attempt += 1
                        
                    else:
                        logger.warning(f"状态查询失败，状态码: {res.status_code}")
                        await asyncio.sleep(polling_interval * 2)  # 失败时延长等待
                        attempt += 1
                        
                except requests.RequestException as e:
                    logger.warning(f"网络请求失败: {e}")
                    await asyncio.sleep(polling_interval * 2)
                    attempt += 1
                except Exception as e:
                    logger.error(f"PDF解析过程中出错: {e}")
                    raise
            
            if attempt >= max_polling_attempts:
                raise TimeoutError(f"PDF解析超时，已轮询{max_polling_attempts}次，任务ID: {sent_info['task_id']}")
        else:
            raise Exception(res.status_code)

    elif mode == "local":
        # 延迟导入minerU相关模块
        from app.kbs.tools.minerU.mineru.cli.common import read_fn
        from app.kbs.tools.minerU.demo.demo import do_parse
        
        file_data = read_fn(pdf_path)
        do_parse(
            output_dir,  # Output directory for storing parsing results
            [filename],  # List of PDF file names to be parsed
            [file_data],  # List of PDF bytes to be parsed
            ['ch']
        )
    print("✅ 解析PDF第一步完成 已解压为md存储")

    base_llm_paras.update({"doc_name":filename})
    await parse_md(output_dir, source_type='md', file_path=os.path.join(output_dir, 'full.md'), base_llm_paras=base_llm_paras)
    print("✅ 解析PDF第二步完成 已通过md_parser获取知识数据")

