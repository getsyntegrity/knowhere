import base64
import io
import re
import os
import uuid
import zipfile
from pathlib import Path
import pandas as pd
import requests
import threading
from io import BytesIO
from PIL import Image
from openai import OpenAI
from loguru import logger
from app.utils.CommonHelper import is_remote, load_file_bytes
from app.services.common.kb_utils import gen_str_codes, path_handle, get_str_time, process_dup_paths_df
from app.services.storage.file_encryptor_service import encryptor
from app.core.config import settings
from app.services.ai.prompt_service import build_prompt
from app.services.ai.response_process_service import eval_response

MD_IMAGE_PATTERN = r'!\[[^\]]*?\]\((.*?\.(?:png|jpe?g|gif))\)'
g_img_lock = threading.Lock()

def image_bytes_to_base64(img_data: bytes, ext: str):
    mime_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")
    # b64_data = base64.b64encode(img_data).decode("utf-8")
    return f"data:{mime_type};base64,{img_data}"

def local_image_to_data_url(path, cut=True, min_size=None, max_size=None):
    from app.core.constants import ProcessingConstants
    if min_size is None:
        min_size = ProcessingConstants.IMG_MIN_SIZE
    if max_size is None:
        max_size = ProcessingConstants.IMG_MAX_SIZE
    if not path.exists():
        logger.warning(f"找不到当前图片路径 {path}")
        return None

    if cut:
        file_size = path.stat().st_size  # 字节
        if file_size < min_size:  # 小于10KB
            logger.debug(f"Skipping {path} (too small: {file_size/1024:.1f} KB)")
            os.remove(path)
            return None
        if file_size >= max_size:  # 大于5MB
            logger.debug(f"Skipping {path} (too large: {file_size/1024/1024:.1f} MB)")
            return None

    with open(path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode("utf-8")
        img_data_base64 = image_bytes_to_base64(img_data, path.suffix.lower())
    return img_data_base64

def detect_images(file_path, valid_extensions=['.png', '.jpg', '.jpeg']):
    if is_remote(file_path):
        response = requests.get(file_path)
        response.raise_for_status()
        file_bytes = BytesIO(response.content)
    else: # file 是本地路径
        file_bytes = open(file_path, 'rb')

    with zipfile.ZipFile(file_bytes, 'r') as zip_ref:
        image_files = [file_info for file_info in zip_ref.infolist()
                       if file_info.filename.startswith('word/media/') and
                       any(file_info.filename.lower().endswith(ext) for ext in valid_extensions)]
    return image_files

def process_img_path4read(paths_, kb_dir, cut):
    urls = []
    for path_ in paths_:
        if not is_remote(path_):
            kb_dir = Path(kb_dir).resolve()
            url_ = local_image_to_data_url(kb_dir / path_, cut)
            if url_ is not None:
                urls.append(url_)
        else:
            urls.append(path_)
    return urls

async def ask_image(client, kb_dir, paths_, title_text="", task="summary-images", query="", max_tokens=None, size_cut=True):
    from app.core.constants import ProcessingConstants
    if max_tokens is None:
        max_tokens = ProcessingConstants.IMG_MAX_TOKENS
    urls_ = process_img_path4read(paths_, kb_dir, size_cut)

    if task == "summary-images":
        image_model = settings.IMAGE_MODEL or "gpt-4-vision-preview"
    else: # 图像提问 和 OCR 使用更好的模型
        image_model = settings.IMAGE_MODEL_MAX or "gpt-4-vision-preview"

    if len(urls_)>0:
        prompt, temperature, top_p, max_tokens = build_prompt(task=task, texts=title_text, query=query, paras={'max_tokens': max_tokens})
        messages = [{
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": prompt
                    }
                ],
            }
        ]
        for url_ in urls_:
            url_header = {
                "type": "image_url",
                "image_url": {
                    "url": url_
                }
            }
            messages[0]['content'].append(url_header)

        try:
            resp = client.chat.completions.create(
                model=image_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p
            )
            resp = resp.choices[0].message.content
            logger.debug(f"图像理解响应: {resp}")
            resp = eval_response(resp)
            return resp
        except Exception as e:
            logger.error(f"理解图像内容失败 原因 {e} 返回结果\n{resp}")
            return None
    else:
        return None

async def detect_summary_img_md(line, last_context, kb_dir, mode=False):
    client = OpenAI(
        api_key=settings.ALI_API_KEY,
        base_url=settings.ALI_URL
    )
    imgs = []
    img_paths = re.findall(MD_IMAGE_PATTERN, line, flags=re.IGNORECASE)
    for i, ip in enumerate(img_paths):
        if mode:
            try:
                image_summary = await ask_image(client, kb_dir, paths_=[ip])
            except:
                image_summary = last_context + str(i)
        else:
            image_summary = last_context + str(i)
        if image_summary is not None:
            imgs.append((ip, image_summary))
    return imgs

async def parse_image(image_path, filename=None, kb_dir=None, baseurl="", base_llm_paras=None, auto_rename=True):
    split_char = settings.SPLIT_CHAR or "-->"
    df_list = []
    time_stamp = get_str_time()
    os.makedirs(kb_dir, exist_ok=True)

    try:
        # 临时保存图像到本地 默认使用filename
        img_path = os.path.join(kb_dir, filename)
        img_bytes = await load_file_bytes(image_path, file_url=baseurl)
        img_obj = Image.open(io.BytesIO(img_bytes))
        if encryptor.encrypt:
            encryptor.save_to_file(img_obj, img_path)
        else:
            img_obj.save(img_path)

        # 提取图像内容
        client = OpenAI(
            api_key=settings.ALI_API_KEY,
            base_url=settings.ALI_URL
        )

        ## 判断图像类别和任务
        img_task = "summary-images"
        from app.core.constants import ProcessingConstants
        img_max_tokens = ProcessingConstants.IMG_MAX_TOKENS
        img_context = f"{filename}\n{base_llm_paras['frag_desc']}"
        type_resp = await ask_image(client, kb_dir, paths_=[filename], title_text=img_context, task="judge-image-type", size_cut=False)
        if type_resp is not None:
            if type_resp["answer"]=="text":
                img_task = "ocr-image"
                img_max_tokens = ProcessingConstants.IMG_OCR_MAX_TOKENS

        if base_llm_paras['summary_image']: # 留出增加上下文的空间 文字辅助理解图
            image_content = await ask_image(client, kb_dir, paths_=[filename], title_text=img_context, task=img_task, max_tokens=img_max_tokens, size_cut=False)
            if image_content is None:
                image_content = filename
        else:
            image_content = filename

        if type_resp["answer"]=="text" and base_llm_paras['summary_image']:
            image_summary = await ask_image(client, kb_dir, paths_=[filename], title_text=filename)
            if image_summary is None:
                image_summary = image_content
        else:
            image_summary = image_content

        # 2. 根据图像内容和文件名决定是否重命名
        img_name = path_handle(image_summary[:20], mode="sanitize")
        img_suffix = os.path.splitext(img_path)[-1]
        if auto_rename:
            update_img_path = os.path.join(kb_dir, f"{img_name}{img_suffix}")
            os.rename(img_path, update_img_path)
        else:
            update_img_path = img_path
    except Exception as e:
        logger.error(f'存储图像失败 因为 {e}...')
        raise

    # 更新并保存本地数据
    img_id = 'IMAGE_' + gen_str_codes(filename + image_content) + '_IMAGE'
    if type_resp["answer"]=="text":
        match_type = '\n'.join([img_id, 'PTXT'])
    else:
        match_type = img_id

    img_bottom_content = f"{img_id}\n上图内容\n{image_content}"
    know_id = gen_str_codes(img_bottom_content + str(uuid.uuid4()))
    update_img_path = split_char.join(update_img_path.split(os.sep))
    df_list.append([img_bottom_content, update_img_path, match_type, len(img_bottom_content), "", image_summary, know_id, "", "", time_stamp])

    all_df_cols = (settings.ALL_DF_COLS or "content,path,type,length,keywords,summary,know_id,tokens,extra,addtime").split(',')
    img_df = pd.DataFrame(df_list, columns=all_df_cols)
    img_df = process_dup_paths_df(img_df)

    if encryptor.encrypt:
        encryptor.save_to_file(img_df, os.path.join(kb_dir, 'KB_PTXT.csv'))
    else:
        img_df.to_csv(os.path.join(kb_dir, 'KB_PTXT.csv'), encoding='utf-8', index=False)


        
        
        
        
        



