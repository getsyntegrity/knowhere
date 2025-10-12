import os
import requests
from app.services.document_parser.md_parser import parse_md
from app.utils.FileDownUpUtils import s3_download_extract_zip


async def parse_pdfs(pdf_path, filename, output_dir, base_llm_paras, mode="api"):
    if mode == "api":
        url = os.environ.get("MINERU_URL")
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ.get('MINERU_API_KEY')}",
        }
        data = {
            "url": pdf_path,
            "is_ocr": True,
            "enable_formula": True,
            "language": "auto"
        }
        res = requests.post(url, headers=header, json=data)
        if res.status_code == 200:
            sent_info = (res.json())["data"]
            status_url = f"https://mineru.net/api/v4/extract/task/{sent_info['task_id']}"
            status_header = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.environ.get('MINERU_API_KEY')}"
            }

            while True:
                res = requests.get(status_url, headers=status_header)
                if res.status_code == 200:
                    status = res.json()["data"]
                    if status['state']=="done":
                        res_zip_url = status['full_zip_url']
                        s3_download_extract_zip(res_zip_url, dest_dir=output_dir, keep_exts=['.md', '.jpg', '.jpeg', '.png', '.gif']) #'.json',
                        break

                    elif status['state']=="running":
                        progress = (status['extract_progress']['extracted_pages'])/(status['extract_progress']['total_pages'])
                        print(f"当前pdf_parse api 进度{progress}")
                else:
                    raise()
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

