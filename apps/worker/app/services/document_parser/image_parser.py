import base64
import io
import os
import re
import threading
import uuid
from pathlib import Path

import pandas as pd
from shared.core.config import settings
from shared.services.ai.prompt_service import build_prompt
from shared.services.ai.response_process_service import eval_response
from app.services.common.kb_utils import (gen_str_codes, get_str_time,
                                          process_dup_paths_df)
from shared.utils.CommonHelperSync import is_remote, load_file_bytes
from shared.utils.file_utils import path_handle
from loguru import logger
from shared.core.exceptions.domain_exceptions import (
    LLMServiceException,
    ImageParsingException,
)
from shared.core.exceptions.knowhere_exception import KnowhereException
from shared.utils.OpenAICompatibleClientSync import OpenAICompatibleClientSync, get_openai_client
from PIL import Image

MD_IMAGE_PATTERN = r'!\[[^\]]*?\]\((.*?\.(?:png|jpe?g|gif))\)'
g_img_lock = threading.Lock()


def _get_vision_client() -> OpenAICompatibleClientSync:
    """Create OpenAI-compatible client for vision models, auto-routing by IMAGE_MODEL name."""
    image_model = settings.IMAGE_MODEL or "qwen-vl-plus"
    return get_openai_client(model=image_model)


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
    from shared.core.constants import ProcessingConstants
    if min_size is None:
        min_size = ProcessingConstants.IMG_MIN_SIZE
    if max_size is None:
        max_size = ProcessingConstants.IMG_MAX_SIZE
    if not path.exists():
        logger.warning(f"Image path not found: {path}")
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


def ask_image(client: OpenAICompatibleClientSync, kb_dir, paths_, title_text="", task="summary-images", query="", max_tokens=None, size_cut=True):
    from shared.core.constants import ProcessingConstants
    if max_tokens is None:
        max_tokens = ProcessingConstants.IMG_MAX_TOKENS
    
    # Filter unsupported formats (sxjg logic)
    valid_exts = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
    valid_paths = []
    for p in paths_:
        ext = os.path.splitext(p)[-1].lower()
        if ext in valid_exts:
            valid_paths.append(p)
        else:
            logger.debug(f"Skipping unsupported image format: {p}")

    if not valid_paths:
        return None
    
    urls_ = process_img_path4read(valid_paths, kb_dir, size_cut)

    if task in ("summary-images", "atlas-page-info"):
        image_model = settings.IMAGE_MODEL or "gpt-4-vision-preview"
    else: # Image Q&A and OCR use better models
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
        resp = ''
        try:
            resp = client.chat_completion(
                messages=messages,
                model=image_model,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
            )
            logger.debug(f"Image understanding response: {resp}")
            resp = eval_response(resp)
            return resp
        except Exception as e:
            logger.error(f"Failed to understand image content: {e}\nResponse: {resp}")
            raise LLMServiceException(
                internal_message=f"Understanding image content failed: {str(e)}",
                provider="openai_image",
                original_exception=e
            )
    else:
        return None


def detect_summary_img_md(line, last_context, kb_dir, mode=False):
    client = _get_vision_client()
    imgs = []
    img_paths = re.findall(MD_IMAGE_PATTERN, line, flags=re.IGNORECASE)
    for i, ip in enumerate(img_paths):
        if mode:
            try:
                image_summary = ask_image(client, kb_dir, paths_=[ip])
            except:
                image_summary = last_context + str(i)
        else:
            image_summary = last_context + str(i)
        if image_summary is not None:
            imgs.append((ip, image_summary))
    return imgs


def parse_image(image_path, filename=None, output_dir=None, baseurl="", base_llm_paras=None, auto_rename=True, relative_root=None):
    split_char = settings.SPLIT_CHAR or "/"
    df_list = []
    time_stamp = get_str_time()
    os.makedirs(output_dir, exist_ok=True)

    try:
        # Save image to local directory temporarily, use filename by default
        img_path = os.path.join(output_dir, filename)
        img_bytes = load_file_bytes(image_path, file_url=baseurl)
        img_obj = Image.open(io.BytesIO(img_bytes))
        img_obj.save(img_path)

        # Extract image content
        client = _get_vision_client()

        ## Determine image category and task
        img_task = "summary-images"
        from shared.core.constants import ProcessingConstants
        img_max_tokens = ProcessingConstants.IMG_MAX_TOKENS
        img_context = f"{filename}\n{base_llm_paras['frag_desc']}"
        type_resp = ask_image(client, output_dir, paths_=[filename], title_text=img_context, task="judge-image-type", size_cut=False)
        if type_resp is not None:
            if type_resp["answer"]=="text":
                img_task = "ocr-image"
                img_max_tokens = ProcessingConstants.IMG_OCR_MAX_TOKENS

        if base_llm_paras['summary_image']: # Leave room for context to help understand the image
            image_content = ask_image(client, output_dir, paths_=[filename], title_text=img_context, task=img_task, max_tokens=img_max_tokens, size_cut=False)
            if image_content is None:
                image_content = filename
        else:
            image_content = filename

        if type_resp["answer"]=="text" and base_llm_paras['summary_image']:
            image_summary = ask_image(client, output_dir, paths_=[filename], title_text=filename)
            if image_summary is None:
                image_summary = image_content
        else:
            image_summary = image_content

        # 2. Decide whether to rename based on image content and filename
        img_name = path_handle(image_summary[:20], mode="sanitize")
        img_suffix = os.path.splitext(img_path)[-1]
        if auto_rename:
            update_img_path = os.path.join(output_dir, f"{img_name}{img_suffix}")
            os.rename(img_path, update_img_path)
            # Store the relative filename for path construction
            final_img_name = f"{img_name}{img_suffix}"
        else:
            update_img_path = img_path
            final_img_name = filename
    except KnowhereException:
        raise
    except Exception as e:
        logger.error(f'Failed to save image: {e}...')
        raise ImageParsingException(
            user_message="Failed to process the image file",
            reason="IMAGE_STORAGE_FAILED",
            internal_message=f"Storage error: {str(e)}",
            original_exception=e
        )

    # Update and save local data
    img_id = 'IMAGE_' + gen_str_codes(filename + image_content) + '_IMAGE'
    if type_resp["answer"]=="text":
        match_type = '\n'.join([img_id, 'PTXT'])
    else:
        match_type = img_id

    img_bottom_content = f"{img_id}\nImage Content:\n{image_content}"
    know_id = gen_str_codes(img_bottom_content + str(uuid.uuid4()))
    # Use relative path with relative_root prefix
    relative_img_path = f"{relative_root}{split_char}{final_img_name}" if relative_root else final_img_name
    df_list.append([img_bottom_content, relative_img_path, match_type, len(img_bottom_content), "", image_summary, know_id, "", "", time_stamp, ""])

    all_df_cols = (settings.ALL_DF_COLS or "content,path,type,length,keywords,summary,know_id,tokens,extra,addtime,page_nums").split(',')
    img_df = pd.DataFrame(df_list, columns=all_df_cols)
    img_df = process_dup_paths_df(img_df)

    return img_df
