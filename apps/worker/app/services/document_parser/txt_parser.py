import re
import uuid
import pandas as pd
from shared.core.config import settings
from shared.services.ai import ai_query_service
from shared.services.ai.prompt_service import build_prompt
from shared.services.ai.response_process_service import eval_response
from shared.utils.CommonHelper import load_file_bytes
from bs4 import BeautifulSoup
from loguru import logger


def clean_texts_by_form(text, form='html'):
    # try html
    soup = BeautifulSoup(text, "html.parser")
    text = soup.get_text(strip=True)
    # try other formats
    return text

async def parse_texts(file_path: str, baseurl: str = "") -> list:
    """Parse text file and return lines list."""
    txt_bytes = await load_file_bytes(file_path, file_url=baseurl)
    text = txt_bytes.decode("utf-8")
    txt_lines = []
    for line in text.splitlines():
        line = re.sub(r'\s', '', line)
        txt_lines.append(line)
    return txt_lines

def divide_long_contents(texts, max_threshold=None, min_threshold=None):
    from shared.core.constants import ProcessingConstants
    if max_threshold is None:
        max_threshold = ProcessingConstants.MAX_THRESHOLD
    if min_threshold is None:
        min_threshold = ProcessingConstants.MIN_THRESHOLD
    sublists = []
    current_sublist = []
    current_word_count = 0
    
    for text in texts:
        word_count = len(text)
        if current_word_count + word_count > max_threshold:
            sublists.append(current_sublist)
            current_sublist = [text]
            current_word_count = word_count
        else:
            current_sublist.append(text)
            current_word_count += word_count
    
    if current_sublist:
        sublists.append(current_sublist)
    
    last_count = sum(len(text) for text in sublists[-1])
    if len(sublists) > 1 and last_count < min_threshold:
        sublists[-2].extend(sublists[-1])
        sublists.pop()
    return sublists, len(sublists)

async def extract_summary_keywords(texts, type_="summary", summary_len=None, keywords_num=None):
    from shared.core.constants import ProcessingConstants
    if summary_len is None:
        summary_len = ProcessingConstants.SUMMARY_LEN
    if keywords_num is None:
        keywords_num = ProcessingConstants.KEYWORDS_NUM
    try:
        if type_ == "summary":
            prompt, temperature, top_p, max_tokens = build_prompt(task='summary', texts=texts, query="", paras={'max_tokens': summary_len})
        elif type_ == "keywords":
            prompt, temperature, top_p, max_tokens = build_prompt(task='summary-keywords', texts=texts, query="", paras={'max_tokens': int(keywords_num*20), 'kw_num': keywords_num})

        messages = [
            {"role": "system", "content": "you are a helpful assistant"},
            {"role": "user", "content": prompt}
        ]

        ctx_task_id = str(uuid.uuid4())
        
        import os
        if os.getenv("LOCAL_DEBUG", "0") != "1":
            from shared.services.redis import RedisServiceFactory
            redis_service = RedisServiceFactory.get_service()
            await redis_service.set(f"task:{ctx_task_id}:status", "processing", ttl=7200)

        resp = await ai_query_service.query_ai(
            messages=messages,
            user_id=ctx_task_id,
            conversation_id=ctx_task_id,
            timeout=90,
            max_tokens=max_tokens
        )
        resp = eval_response(resp)

        if type_ == "keywords":
            if isinstance(resp, dict):
                return resp.get('answer', resp)
            return resp
        else:
            return resp

    except Exception as e:
        print(f"❌ failed to extract summary or keywords {e}")
        return ""

async def postprocess_leaf_dics(dict_list, llm_paras, merge_key='heading', content_key='content', summary_len=None):
    from shared.core.constants import ProcessingConstants
    if summary_len is None:
        summary_len = ProcessingConstants.POSTPROCESS_SUMMARY_LEN
    
    merged_dict = {}
    split_char = settings.SPLIT_CHAR or "/"
    for identifier, d in dict_list:
        identifier = split_char.join(identifier)
            
        if identifier in merged_dict:
            merged_dict[identifier][content_key].extend(d[content_key])
        else:
            merged_dict[identifier] = {merge_key: d[merge_key], content_key: list(d[content_key])}
    
    merged_list = [(identifier, v['content']) for identifier, v in merged_dict.items()]
    merge_df = pd.DataFrame(merged_list, columns=['path_identifier', 'content_lst'])
    merge_df['path'] = merge_df['path_identifier'].apply(lambda x:x.split(split_char))
    merge_df = merge_df[['path', 'content_lst', 'path_identifier']]    

    # TODO rough dividing of contents (need more smart dividing)
    df_with_divides = pd.DataFrame(columns=['path', 'content_lst', 'path_identifier'])
    for i, row in merge_df.iterrows():
        if len(row['path'])==0:
            continue

        local_contents = row['content_lst']
        if len(local_contents)>0 and not llm_paras['doc_type'] in "templates":
            sublists, num = divide_long_contents(local_contents, max_threshold=int(3*summary_len))
        else:
            num = 0

        if num<=1:
            df_with_divides.loc[len(df_with_divides)] = row
        else:
            head = row['path_identifier']
            if not head:
                head = '**Preface**'
            for k in range(num):
                sub_head = head + split_char + head.split(split_char)[-1] + " part " + str(k+1)
                df_with_divides.loc[len(df_with_divides)] = {'path':sub_head.split(split_char), 'content_lst':sublists[k], 'path_identifier':sub_head}

    # generate summary and keywords for bottom nodes
    df_with_labels = pd.DataFrame(columns=['path', 'content_lst', 'path_identifier', 'keywords', 'local_summary'])
    pattern = re.compile(r'(TABLE_.*?_TABLE|IMAGE_.*?_IMAGE)')
    for i, row in df_with_divides.iterrows():
        contents4summary = re.sub(pattern, '', '\n'.join(row['content_lst']))
        keywords = ""
        summary = ""

        if len(contents4summary)>summary_len and llm_paras["summary_txt"] and (not llm_paras['doc_type'] in "templates"):
            summary = await extract_summary_keywords(contents4summary, type_="summary")
            keywords = await extract_summary_keywords(contents4summary, type_="keywords")

        df_with_labels.loc[len(df_with_labels)] = {'path': row['path'],
                                                   'content_lst': row['content_lst'],
                                                   'path_identifier': row['path_identifier'],
                                                   'keywords': keywords,
                                                   'local_summary': summary
                                                   }
    return df_with_labels
