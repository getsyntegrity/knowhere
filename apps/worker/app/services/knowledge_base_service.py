import json
import os
import re
import uuid

import numpy as np
import pandas as pd
from app.core.config import settings
from app.core.context import get_current_user
from app.core.dependencies import get_redis_service
from app.models.database.user import User
from app.services.ai import ai_query_service
from app.services.ai.prompt_service import build_prompt
from app.services.ai.response_process_service import eval_response
# ARQ依赖已移除，使用Celery替代
from app.services.common.global_manager_service import (global_df_manager,
                                                        global_dict_manager,
                                                        global_vector_manager)
from app.services.common.kb_utils import (clean_contents, create_reply,
                                          expand_summary_paths,
                                          gen_sim_matrix,
                                          gen_str_codes, merge_df,
                                          restore_graph_by_paths)
from app.services.document_parser.doc_parser import (convert_doc2dics,
                                                     parse_docx)
from app.services.document_parser.image_parser import ask_image, parse_image
from app.services.document_parser.md_parser import parse_md
from app.services.document_parser.table_parser import (clean_html_tb,
                                                       html_to_md_lines,
                                                       parse_xlsx,
                                                       table_scope_analyze)
from app.services.document_parser.txt_parser import parse_texts
from app.services.knowledge.encoder_finetuner import \
    gen_train_data_from_interactions
from app.services.knowledge.query_enhancer_service import label_queries
# 延迟导入PDF解析器
from app.services.knowledge.rag_service import (find_closest, merge_paths_soft,
                                                rerank_, vectorize_texts)
from app.services.storage.file_encryptor_service import encryptor
from app.utils.CommonHelper import is_remote
from app.utils.file_utils import path_handle
from app.utils.llm_utils import use_llm_api
from app.utils.text_utils import remove_duplicates_orderkept
from loguru import logger
from openai import OpenAI


async def build_sim_matrix(user, source_node, topk=5, min_threshold=0.2):
    filter_path_vecs, _, filter_content_vecs, filter_contents_df = checkerboard_filter_kb(user, signal_paths=['templates'], filter_mode='delete',
                                                                target_types=['PTXT', '_TABLE', '_IMAGE'])
    masks = filter_contents_df['path'].str.contains(source_node, na=False, regex=False)
    self_ids = np.where(masks)[0].tolist() # 注意这里不能直接用filter_contents_df的index因为那些是整个 all_contents_df的对应位置

    top_content_ids, cthd = await gen_sim_matrix(filter_content_vecs, self_ids, topk, pre_threshold=min_threshold)
    top_path_ids, pthd = await gen_sim_matrix(filter_path_vecs, self_ids, topk, pre_threshold=min_threshold)

    merged_ids = np.concatenate([top_content_ids, top_path_ids], axis=1)  # (n, m*k)
    n, m = merged_ids.shape
    dedup_ids = merged_ids.copy()

    for i in range(n):
        row = merged_ids[i]
        uniq, idx = np.unique(row, return_index=True) # 找到唯一值及其首次出现位置
        idx = np.sort(idx)
        mask = np.ones_like(row, dtype=bool)
        mask[idx] = False  # 这些位置是合法的
        dedup_ids[i][mask] = -1  # 其他重复值设为 -1
    return dedup_ids, filter_contents_df, m

def filter_path(current_df, signal_paths: list, remain_paths: list, mode="delete"):
    if mode=="delete":
        filter_path_ids = [
            i for i, path in enumerate(remain_paths)
            if not any(keyword in path for keyword in signal_paths)
        ]
    elif mode=="keep":
        filter_path_ids = [
            i for i, path in enumerate(remain_paths)
            if any(keyword in path for keyword in signal_paths)
        ]
    else:
        raise ValueError(f"不支持的过滤模式: {mode}")

    filter_paths = [remain_paths[i] for i in filter_path_ids]
    df_mask = current_df["path"].apply(lambda p: any(fp in p for fp in filter_paths))
    filter_content_df = current_df[df_mask].copy()
    filter_content_ids = current_df.index[df_mask].tolist()
    return filter_paths, filter_path_ids, filter_content_df, filter_content_ids

def filter_path_type(df: pd.DataFrame, target_types=None):
    def match_type(type_str):
        parts = str(type_str).strip().split("\n")
        return all(any(part.endswith(t) for t in target_types) for part in parts)

    if target_types is None:
        target_types = []
    mask = df["type"].apply(match_type)
    remain_paths = remove_duplicates_orderkept(df.loc[mask, 'path'].tolist())
    return df[mask], remain_paths

def checkerboard_filter_kb(user, signal_paths, target_types, filter_mode):
    all_vec = global_vector_manager.get_vector(user['user'] + '_all_contents_vec')
    all_path_vec = global_vector_manager.get_vector(user['user'] + '_all_path_vec')
    all_contents_df = global_df_manager.get_dataframe(user['user'] + '_all_contents_df')

    # 首先进行类别过滤
    remain_df, remain_paths = filter_path_type(all_contents_df, target_types)

    # 然后进行路径过滤
    filter_paths, filter_path_ids, filter_content_df, filter_content_ids = filter_path(remain_df, signal_paths, remain_paths, mode=filter_mode)
    if len(filter_paths)==0:
        return {}, [], [], [], [], [], []

    filter_path_vecs = all_path_vec[filter_path_ids].astype(np.float32)
    filter_all_vec = all_vec[filter_content_ids].astype(np.float32)
    return filter_path_vecs, filter_paths, filter_all_vec, filter_content_df

async def checkerboard_find(user, user_message, topk=None, final_topk=-1, rerank=False, signal_paths=[], data_type=1, filter_mode="delete", threshold=0):
    def cut_path(p, root_len):
        if isinstance(p, str):
            split_char = settings.SPLIT_CHAR or ";"
            return split_char.join(p.split(split_char)[root_len:])
        return p

    client = OpenAI(
        api_key=settings.ALI_API_KEY,
        base_url=settings.ALI_URL
    )

    hybrid = user['USER_SETTINGS']['HYBRID_SEARCH']
    if topk is None:
        topk = user['USER_SETTINGS']['TOP_K']

    punc_pattern = r'[\.,?!;:"\'\[\]\(\)\{\}，？！；：“”‘’【】（）]'
    user_message = re.sub(punc_pattern, '', user_message)
    user_message, q_vector = vectorize_texts(user_message, client=client)

    if not signal_paths:
        signal_paths = user['USER_SETTINGS']['PATHS_IGNORE']

    if data_type==1:
        target_types = ['PTXT', '_TABLE', '_IMAGE', '_SUMMARY']  # 默认图文表并茂
    elif data_type==2: # 只要文字
        target_types = ['PTXT']
    elif data_type==3: # 只要图
        target_types = ['_IMAGE']
    elif data_type==4: # 只要表
        target_types = ['_TABLE']
    elif data_type==5: # 只要 summary
        target_types = ['_SUMMARY']
    elif data_type==6: # 只要文+图
        target_types = ['_IMAGE', 'PTXT']
    elif data_type==7: # 只要文+表
        target_types = ['_TABLE', 'PTXT']
    elif data_type==8: # 只要 summary+文
        target_types = ['_SUMMARY', 'PTXT']
    elif data_type==9: # 只要 summary+文+图
        target_types = ['_SUMMARY', 'PTXT', '_IMAGE']
    elif data_type==10: # 只要 summary+文+表
        target_types = ['_SUMMARY', 'PTXT', '_TABLE']
    elif data_type==11: # 不要summary
        target_types = ['PTXT', '_TABLE', '_IMAGE']
    else:
        raise ValueError(f"不支持的数据类型: {data_type}")

    path_vecs, all_paths, content_vecs, all_contents_df = checkerboard_filter_kb(user, signal_paths, target_types, filter_mode)
    all_contents = all_contents_df['content'].tolist()
    all_contents_tokens = all_contents_df['tokens'].fillna("").tolist()

    # 1. find by path searching
    sim_paths_pa, sim_ids_pa, scores_pa, _ = await find_closest(all_paths, path_vecs, q_vector, topk, msg=user_message, hybrid=hybrid,
                                                                stopwords=user['stopwords'], threshold=threshold)
    # 2. find by content voting
    _, sim_ids_con, scores_con, sim_paths_con = await find_closest(all_contents, content_vecs, q_vector, topk, msg=user_message, add_identifiers=all_paths,
                                                    hybrid=hybrid, stopwords=user['stopwords'], token_corpus=all_contents_tokens, threshold=threshold)
    # 3. merge results by weighting
    zips_pa = zip(sim_ids_pa, scores_pa)
    zips_con = zip(sim_ids_con, scores_con)
    sim_ids_merge, scores_merge = merge_paths_soft(zips_pa, zips_con, con_weight=3)

    # 4. rerank to improve the results, taking additional seconds
    merge_df = all_contents_df.iloc[sim_ids_merge][["path", "content", "summary"]].fillna("")
    merge_df["content"] = clean_contents(merge_df["content"])
    paths4rank = merge_df['path'].tolist() # 获取知识点的系统路径 从 ./users开始

    if rerank:
        root_len = user['USER_SETTINGS']['ROOT_LEN']
        merge_df["path"] = merge_df["path"].apply(lambda p: cut_path(p, root_len))
        rerank_df = merge_df.copy(deep=True)
        rerank_df["merged_text"] = rerank_df["summary"] + " " + rerank_df["content"]
        rerank_df["merged_text"] = rerank_df["merged_text"].apply(lambda x: " ".join(x.split()[:200]))

        rerank_df = rerank_df.drop(columns=["content", "summary"])
        rerank_df.insert(0, "序号", range(1, len(rerank_df) + 1))
        rerank_df.columns = ['序号', '知识路径', '知识点摘要']
        rerank_html = rerank_df.to_html(index=False, escape=False)
        merged_paths = await rerank_(rerank_html, user_message, paths4rank, keep_one=True)
    else:
        merged_paths = merge_df['path'].tolist()

    if final_topk>0:
        merged_paths = merged_paths[:final_topk]
    else:
        merged_paths = merged_paths[:topk]

    reply_paths = create_reply(merged_paths, user_message)
    response_data = {
        'reply':reply_paths, # 前端打印找到的路径和片段名
        'sim_contents':merged_paths
    }
    return response_data

def matching_df(sub_path, all_contents_df, USER_SETTINGS, summary_term='-->摘要总结', save_session=False):
    ini_filtered_df = all_contents_df[all_contents_df['path'].str.contains(sub_path, na=False, regex=False)]
    if ini_filtered_df.empty:
        raise "❌ 未能根据sim paths找到contents_df片段 检查返回的知识路径"

    match_dfs = pd.DataFrame(columns=list(all_contents_df.columns))
    summary_texts = []
    parent_nodes = set()
    for _, row in ini_filtered_df.iterrows():
        if '_SUMMARY' in row['type']:
            parent_node = re.findall(r'SUMMARY_(.*?)_SUMMARY', row['type'])[0]
            if parent_node in parent_nodes:
                continue
            parent_nodes.add(parent_node)

            summary_paths, summary_df = expand_summary_paths(all_contents_df, parent_node, summary_term)
            if not summary_df['path'].isin(match_dfs['path']).any():
                match_dfs = pd.concat([match_dfs, summary_df], ignore_index=True)
                # ****if we have multiple summary term, we only record the last one, which can be incorrect
            summary_graph, summary_texts = restore_graph_by_paths(summary_paths)
        else:
            match_dfs.loc[len(match_dfs)] = row

    if save_session:
        exist_match_dfs = pd.read_csv(USER_SETTINGS['MATCH_DF'], encoding='utf-8', keep_default_na=False)
        all_match_dfs = pd.concat([exist_match_dfs, match_dfs], ignore_index=True)
        all_match_dfs.to_csv(USER_SETTINGS['MATCH_DF'], mode='a', index=False, encoding='utf-8', header=False)
    return match_dfs, '\n'.join(summary_texts)

def build_context(know_df, resource_dict, used_images, used_tables, KB_PATH, show_image=True, long_table_limit=20000):
    context = ''
    for i, row in know_df.iterrows():
        row_type = row['type']

        if 'PTXT' in row_type:
            context += row['content']

        if 'TABLE_' in row_type:
            tb_targets = row_type.split('\n')
            for tb_id in tb_targets:
                if 'TABLE_' in tb_id and not tb_id in used_tables:
                    tb_path = resource_dict[tb_id]['path']
                    tb_str = read_tb_from_kb(os.path.join(KB_PATH, tb_path), return_mode="html")

                    if len(tb_str) > long_table_limit:
                        logger.warning(f'表格文本过长{len(tb_str)} 超过限制{long_table_limit} \t嵌入表格路径 后续将使用表格理解智能体...')
                        tb_str = f'TABLEPATH_{tb_path}_TABLEPATH'

                    if tb_id in context:
                        context = re.sub(tb_id, tb_str, context) # 如果表格小就直接替换
                    else:
                        context = context + f"\n找到以下表格\n{tb_str}\n"
                    used_tables.append(tb_id)

        if 'IMAGE_' in row_type:
            img_targets = row_type.split('\n')
            for img_id in img_targets:
                if 'IMAGE_' in img_id and not img_id in used_images:
                    if show_image:
                        img_path = resource_dict[img_id]['path']
                        img_str = f'IMAGEURL_{img_path}_IMAGEURL'

                        if img_id in context:
                            context = re.sub(img_id, img_str, context)
                        else:
                            context = context + f"\n找到以下图片\n{img_str}\n"
                    else:
                        context = re.sub(img_id, "", context) # 如果不展示图片 直接替换为空字符串
                    used_images.append(img_id)
    return context.strip(), used_images, used_tables

def checkerboard_integrate_contents(user, sim_paths, save_session=False, show_image=True, limit=200000):
    all_contents_df = global_df_manager.get_dataframe(user['user'] + '_all_contents_df')
    resource_dict = global_dict_manager.get_dict(user['user'] + '_resource_dict')

    integrated_contents = ""
    integrated_summary = ""
    temp_contents = ""
    temp_summary = ""
    used_images = []
    used_tables = []
    count_ = 1
    while True and len(sim_paths) > 0:
        sub_path = sim_paths.pop(0)
        split_char = settings.SPLIT_CHAR or ";"
        show_path = split_char.join(sub_path.split(split_char)[user['USER_SETTINGS']['ROOT_LEN']:])
        match_dfs, sub_summary = matching_df(sub_path, all_contents_df, user['USER_SETTINGS'], save_session=save_session)
        merged_df = merge_df(match_dfs)

        sub_content, used_images, used_tables = build_context(merged_df, resource_dict, used_images, used_tables, user['KB_PATH'], show_image)
        if sub_content.strip():
            temp_contents = f"{integrated_contents}\n\n【第{count_}条知识片段】:\n【知识库路径】:{show_path}\n【知识内容】:\n{sub_content}"
        if sub_summary.strip():
            temp_summary = f"{integrated_summary}\n\n【第{count_}组总结摘要】:\n{sub_summary}"

        if len(temp_contents) + len(temp_summary) > limit:
            if not integrated_contents: # 如果第一轮就超限了 inte_contents还是空的
                return temp_contents, temp_summary
            else:
                break
        else:
            integrated_contents = temp_contents
            integrated_summary = temp_summary
        count_ += 1
    return integrated_contents, integrated_summary

async def talk2kb(query, context, paras):
    prompt, temperature, top_p, max_tokens = build_prompt(task="talk-kb", texts=context, query=query, paras=paras)
    messages = [
        {"role": "system", "content": "你是一个有帮助的助手"},
        {"role": "user", "content": prompt}
    ]

    ctx_task_id = gen_str_codes((str(uuid.uuid4()) + query))
    
    # 使用Redis直接追踪任务状态，无需数据库持久化
    redis_service = await get_redis_service()
    await redis_service.set(f"task:{ctx_task_id}:status", "processing", ttl=7200)
    
    # 使用统一的AI查询服务
    ask_res = await ai_query_service.query_ai(
        messages=messages,
        user_id=ctx_task_id,
        conversation_id=ctx_task_id,
        timeout=60
    )
    answer = eval_response(ask_res)
    
    # 更新任务状态为完成
    await redis_service.set(f"task:{ctx_task_id}:status", "completed", ttl=7200)
    
    return answer

async def talk2kb_mm(query, context, paras):
    client = OpenAI(
        api_key=settings.ALI_API_KEY,
        base_url=settings.ALI_URL
    )
    mm_answers = []
    mm_cols = []
    img_paths = re.findall(r'IMAGEURL_(.*?)_IMAGEURL', context)
    tb_paths = re.findall(r'TABLEPATH_(.*?)_TABLEPATH', context)
    text_context = re.sub(r'(IMAGEURL_.*?_IMAGEURL|TABLEURL_.*?_TABLEURL)', '', context, flags=re.DOTALL)

    # 1. 基于文本回答 如果不涉及图和宽表
    if text_context.strip() != '' and (len(img_paths)==0 and len(tb_paths)==0):
        answer_from_text = await talk2kb(query, text_context, paras)
        mm_answers.append(answer_from_text)
        mm_cols.append("文本信息")

    # 2. 基于图像（文本+图像）回答
    img_resp = await ask_image(client, paras['kb_path'], img_paths, title_text=text_context, task="ask-image", query=query, size_cut=False)
    if img_resp is not None:
        if not img_resp['answer']=="null":
            mm_answers.append(img_resp['answer'])
            mm_cols.append("图文信息")

    # 3. underdevelopment 基于表格或其他模态回答
    for tb_path in tb_paths:
        tb_context = await table_scope_analyze(query, os.path.join(paras['kb_path'], tb_path), paras)
        if tb_context is not None:
            paras.update({'add_req': "回答完善准确，需要包括一定的解释说明"})
            # *******UNDER DEVELOPMENT****** 表格操作（现在只是问 后续支持数据分析）
            tb_answer = await talk2kb(query, tb_context, paras)
            if not "知识库暂无相关资料" in tb_answer:
                mm_answers.append(tb_answer)
                mm_cols.append("表格信息")

    # 4. 深度研究-整理结论
    if len(mm_answers) > 0:
        task_query = f"调研 {query}"
        ds_df = pd.DataFrame([mm_answers], columns=mm_cols)
        ds_df.insert(0, '查询语句', [query])
        ds_df = ds_df.set_index('查询语句')
        ds_df.columns = pd.MultiIndex.from_product([['模态'], ds_df.columns])
        ds_html = (
            ds_df.style.set_table_styles([
                dict(selector='td', props=[('white-space', 'pre-wrap')]),
                dict(selector='th', props=[('white-space', 'pre-wrap')]),
            ])
            .to_html()
        )

        prompt, temperature, top_p, max_tokens = build_prompt(task="merge-answers", texts=ds_html, query=task_query, paras=paras)
        messages = [
            {"role": "system", "content": "你是一个有帮助的助手"},
            {"role": "user", "content": prompt}
        ]

        ctx_task_id = gen_str_codes((str(uuid.uuid4()) + query))
        
        # 使用Redis直接追踪任务状态，无需数据库持久化
        redis_service = await get_redis_service()
        await redis_service.set(f"task:{ctx_task_id}:status", "processing", ttl=7200)
        
        # 使用统一的AI查询服务
        ask_res = await ai_query_service.query_ai(
            messages=messages,
            user_id=ctx_task_id,
            conversation_id=ctx_task_id,
            timeout=60
        )
        answer = eval_response(ask_res)
        
        # 更新任务状态为完成
        await redis_service.set(f"task:{ctx_task_id}:status", "completed", ttl=7200)
    else:
        answer = r"【知识库暂无相关资料，我们会持续完善】"
    return answer

async def checkerboard_filling_tb(user, keyword, type, tb_texts, api_name='qwen_api', model_name='qwen-plus'):
    if type=="KV":
        task = 'filling-tb-kv'
    elif type=="CLICK":
        task = 'filling-tb-ck'
    response, llm_histories = await use_llm_api(user.llm_apis[api_name],
                                            histories=user.llm_histories,
                                            paras={ 'task':task,
                                                    'query':keyword,
                                                    'texts':tb_texts,
                                                    'local_model_name':user['USER_SETTINGS']['LOCAL_LLM_NAME'],
                                                    'model':model_name,
                                                    'local_model':user.local_llm,
                                                    'local_tz': user.local_llm_tz,
                                                    'use_his':False },
                                            config=user['model_config'])
    try:
        answer = response['answer']
    except:
        answer = response
    return answer

def checkerboard_qlabel(user, query, qlabel, api_name='qwen_api'):
    fuzzy_warning = '系统侦测到您的提问可能过于模糊，可能影响回答质量，请考虑是否优化提问。'
    if qlabel:
        labeled_queries = []
        queries = [query] # UNDER DEVELOPMENT: divide a query into multiple ones if possible
        temp_labels = label_queries(queries, user['model_config'], user['USER_SETTINGS'], user.llm_histories, api_name=None)

        for lq in temp_labels:
            if lq[1]=='fuzzy':
                labeled_queries.append({'query':lq[0], 'predefined_res':fuzzy_warning})
            else:
                labeled_queries.append({'query':lq[0], 'predefined_res':''})

        return labeled_queries
    else:
        return [{'query':query, 'predefined_res':''}]

async def checkerboard_inject_parse(
    file_full_path, 
    filename, 
    user_config: dict = None,  # 新增参数：可选的用户配置
    **kwargs
):
    """
    解析文档
    
    Args:
        file_full_path: 文件完整路径
        filename: 文件名
        user_config: 用户配置字典（可选，如果不提供则从上下文获取）
        **kwargs: 其他参数
    
    Returns:
        解析后的目录路径
    """
    # 如果没有传入user_config，则从上下文获取（兼容旧调用方式）
    if user_config is None:
        user_context: User | None = get_current_user()
        redis_service = await get_redis_service()
        from app.services.redis.user_redis_service import UserRedisService
        user_redis_service = UserRedisService(redis_service)
        
        if not user_context:
            raise ValueError("用户上下文为空")
        
        user_config = await user_redis_service.get_user_config(str(user_context.id))
        if not user_config:
            import json

            from app.services.user.user_config_service import UserConfigService
            user_dic_str = UserConfigService.init_user(str(user_context.id))
            user = json.loads(user_dic_str) if isinstance(user_dic_str, str) else user_dic_str
            await user_redis_service.save_user_config(str(user_context.id), user)
        else:
            user = user_config
    else:
        # 使用传入的user_config
        user = user_config
    
    # 构建base_llm_paras
    base_llm_paras = {
        "llm_histories": user['USER_SETTINGS']['llm_histories'],
        "smart_title_parse": kwargs.get('smart_title_parse', True),
        "summary_image": kwargs.get('summary_image', True),
        "summary_table": kwargs.get('summary_table', True),
        "summary_txt": kwargs.get('summary_txt', True),
        "stopwords": user.get('stopwords', []),
        "doc_type": kwargs.get('doc_type', 'auto'),
        "frag_desc": kwargs.get('add_frag_desc', ''),
    }
    
    try:
        baseurl = kwargs.get('base_url', '')
    except:
        baseurl = ""
        
    logger.debug(f"baseurl: {baseurl}")
    logger.debug(f"file_full_path: {file_full_path}")

    if is_remote(file_full_path):
        # 如果已经是完整的URL（预签名URL），直接使用
        # 不需要调用 get_pub_fileurl()
        pass # TODO: 后续需要处理
    # 对于本地文件，保持原始路径，不要替换为.fragment
    # file_full_path 保持原值

    split_char = settings.SPLIT_CHAR or ";"
    kb_dir = kwargs.get('kb_dir', '默认目录')
    dir_terms = kb_dir.split(split_char)
    dir_terms.insert(0, user['KB_PATH'])
    filename = path_handle(filename, mode="clean_single")
    
    if not "images" in dir_terms and filename is not None:
        dir_terms.append(filename)

    kb_dir = path_handle(os.path.join(*dir_terms), mode="sanitize")
    os.makedirs(kb_dir, exist_ok=True)

    # 根据文件类型解析
    if '.txt' in file_full_path or ".fragment" in file_full_path:
        logger.debug(f"file type is txt or fragment")
        try:
            fragment_content = kwargs.get('fragment_content')
        except:
            fragment_content = None
        txt_lines = await parse_texts(file_path=file_full_path, fragment_content=fragment_content, baseurl=baseurl)
        await parse_md(kb_dir, source_type='md', md_lines=txt_lines, base_llm_paras=base_llm_paras)

    elif ('.png' in file_full_path or '.jpg' in file_full_path or '.jpeg' in file_full_path) or ".fragment" in file_full_path:
        logger.debug(f"file type is image")
        await parse_image(file_full_path, filename=filename, kb_dir=kb_dir, baseurl=baseurl, base_llm_paras=base_llm_paras)

    elif '.pdf' in file_full_path:
        logger.debug(f"file type is pdf")
        if filename is not None and file_full_path is not None:
            from app.services.document_parser.pdf_parser import parse_pdfs
            await parse_pdfs(file_full_path, filename=filename, output_dir=kb_dir, base_llm_paras=base_llm_paras, mode="api")

    elif '.docx' in file_full_path:
        logger.debug(f"file type is docx")
        if filename is not None and file_full_path is not None:
            parsed_structure, df_list = await parse_docx(file_full_path, base_llm_paras, kb_dir, filename, baseurl)
            await convert_doc2dics(parsed_structure, df_list, kb_dir, base_llm_paras=base_llm_paras)

    elif '.xlsx' in file_full_path:
        logger.debug(f"file type is xlsx")
        if filename is not None and file_full_path is not None:
            await parse_xlsx(file_full_path, filename, kb_dir, baseurl, base_llm_paras=base_llm_paras)

    elif '.pptx' in file_full_path:
        logger.debug(f"file type is pptx")
        if filename is not None and file_full_path is not None:
            from app.services.document_parser.pdf_parser import parse_pdfs
            await parse_pdfs(file_full_path, filename=filename, output_dir=kb_dir, base_llm_paras=base_llm_paras, mode="api")

    elif '.md' in file_full_path:
        logger.debug(f"file type is md")
        if filename is not None and file_full_path is not None:
            await parse_md(kb_dir, source_type="md", file_path=file_full_path, base_llm_paras=base_llm_paras)

    elif '.json' in file_full_path:
        logger.debug(f"file type is json")
    logger.debug(f"kb_dir: {kb_dir}")
    return kb_dir

def checkerboard_learn(user, reply, user_intention, sim_contents, user_selected_ids, current_markers):
    # 改造为微调大模型
    local_train_data = gen_train_data_from_interactions(user['USER_SETTINGS'],
                                                        user_intention,
                                                        sim_contents,
                                                        user_selected_ids,
                                                        all_contents_df=user['all_contents_df'],
                                                        mode='both',
                                                        add_neg=10)

    if user['USER_SETTINGS']['BN_RL'] and (
            len(local_train_data) >= user['USER_SETTINGS']['N_TRIGGER'] and len(local_train_data) %
            user['USER_SETTINGS']['N_TRIGGER'] == 0):
        # fine-tune global encoder
        user.fine_tuner.model_setting()
        user.fine_tuner.model_finetuning()
        user.fine_tuner.model_fusing()
        # train local reasoner
        user.opt_memory.eval(len(reply),
                             user_intention,
                             sim_contents,
                             user_selected_ids,
                             current_markers)

def read_tb_from_kb(tb_path, return_mode="html"):
    with open(tb_path, "r", encoding="utf-8") as f:
        tb_html = f.read()
        tb_html = clean_html_tb(tb_html)
    if return_mode == "html":
        return tb_html
    elif return_mode == "md":
        return html_to_md_lines(tb_html)
    else:
        raise Exception("只能返回html或者md")

def read_img_from_kb(img_record, img_id, KB_PATH):
    split_char = settings.SPLIT_CHAR or ";"
    img_path = (img_record[img_id]).replace(split_char, os.path.sep)
    img_path = os.path.join(KB_PATH, img_path)
    img_data = None
    if encryptor.encrypt:
        img_data = encryptor.load_from_file(img_path)
    else:
        with open(img_path, 'rb') as fd:
            img_data = fd.read()
    return img_data

def encapsulate_json(df, kb_dir):
    def safe_int(x):
        if pd.isna(x): return 0
        try:
            return int(float(x))
        except:
            return 0

    def safe_split_kws(kw):
        if pd.isna(kw): return []
        return [k.strip() for k in str(kw).split(";") if k.strip()]

    def safe_parse_rels(type_, connects):
        rels_ = type_.split("\n")[1:-1]
        if not pd.isna(connects):
            rels_.extend(connects.split("\n"))
        return rels_

    chunks = []
    for _, row in df.iterrows():
        chunk = {
            "chunk_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, str(row.get("know_id", uuid.uuid4())))),
            "content": str(row.get("content", "")),
            "path": str(row.get("path", "")),
            "metadata": {
                "keywords": safe_split_kws(row.get("keywords")),
                "summary": str(row.get("summary", "")),
                "length": safe_int(row.get("length")),
                "tokens": safe_int(row.get("tokens")),
                "relationships": safe_parse_rels(row.get("type"), row.get("connectto"))
            }
        }

        if row.get("type").startswith("PTXT"):
            chunk.update({"type": "text"})

        elif row.get("type").startswith("IMAGE_"):
            chunk.update({"type": "image"})
            img_name = chunk.get("path").split("-->")[-1]
            chunk.get("metadata").update({
                "file_path": f"images/{img_name}",
                "original_name": img_name
            })

        elif row.get("type").startswith("TABLE_"):
            chunk.update({"type": "table"})
            tbl_name = chunk.get("path").split("-->")[-1]
            chunk.get("metadata").update({
                "file_path": f"images/{tbl_name}",
                "original_name": tbl_name
            })
        chunks.append(chunk)

    output_path = os.path.join(kb_dir, 'chunks.json')
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=4)

# async def checkerboard_create_know(user, dir_name, content, inner_key, resource={}, mode="append"):
#     ''' function add new individual knowledge or inject knowledge to existing structure '''
#
#     if user['USER_SETTINGS']['USE_LOCAL_LLM']: # this function supports local_llm
#         api_name = 'local_api'
#
#     kb_dir = os.path.join(user['KB_PATH'], dir_name.replace(settings.SPLIT_CHAR, os.path.sep))
#     if not os.path.exists(kb_dir):
#         os.mkdir(kb_dir)
#         # with open(os.path.join(kb_dir, "image_record.json"), "w", encoding="utf-8") as f:
#         #     json.dump({}, f, ensure_ascii=False, indent=4)
#         # with open(os.path.join(kb_dir, "table_record.json"), "w", encoding="utf-8") as f:
#         #     json.dump({}, f, ensure_ascii=False, indent=4)
#
#     kb_path = os.path.join(kb_dir, 'KB_PTXT.csv')
#     if not os.path.exists(kb_path):
#         doc_df = pd.DataFrame(columns=user['know_df_cols'])
#     else:
#         if encryptor.encrypt:
#             doc_df = encryptor.load_from_file(kb_path)
#         else:
#             doc_df = pd.read_csv(kb_path, index_col=False, encoding='utf-8')
#
#     pattern = re.compile(r'(TABLE_.*?_TABLE|IMAGE_.*?_IMAGE)')
#     matches = pattern.findall(content)
#     if len(matches)==0:
#         matches = 'NOLINK'
#     else:
#         matches = '\n'.join(matches)
#
#     keywords = []
#     local_summary = ''
#     if len(content)>user['USER_SETTINGS']['SUMMARY_THRESHOLD'] and user['USER_SETTINGS']['LOCAL_SUMMARY']:
#         keywords = await extract_summary_keywords(content, type_="keywords")
#
#     know_dic, know_id = process_full_contents(content, inner_key)
#     keywords_str = ' '.join(keywords)
#     if inner_key in doc_df['path'].values:
#         idx = doc_df[doc_df['path'].astype(str)==inner_key].index[0]
#
#         if mode=="replace":
#             doc_df.loc[idx, ['linkage', 'summary', 'keywords', 'know_id']] = [
#                 matches, local_summary, keywords_str, know_id
#             ]
#         elif mode=="append":
#             exist_row = doc_df.iloc[idx]
#             exist_know_dic = json.loads(exist_row['content'])
#             exist_contents = extract_nested_dic_vals(exist_know_dic)
#             enrich_lst = extract_nested_dic_vals(know_dic)
#             exist_contents.extend(enrich_lst)
#             update_know, know_id = process_full_contents(("".join(exist_contents)).strip(), inner_key)
#             # update_know = exist_know_dic
#         elif mode=="enrich":
#             raise("under development")
#
#         doc_df.at[idx, 'content'] = json.dumps(update_know, ensure_ascii=False, indent=4)
#         doc_df.at[idx, 'know_id'] = know_id
#     else:
#         # 如果 path 不存在，追加新行
#         know_dic = json.dumps(know_dic, ensure_ascii=False, indent=4)
#         temp_df = pd.DataFrame({'path':[inner_key],
#                                 'content':[know_dic],
#                                 'linkage':[matches],
#                                 'summary':[local_summary],
#                                 'keywords':[keywords_str],
#                                 'know_id':[know_id]})
#         doc_df = pd.concat([doc_df, temp_df], ignore_index=True)
#
#     doc_df = process_dup_paths_df(doc_df)
#     logger.info('kb_path:{}', kb_path)
#     if encryptor.encrypt:
#         encryptor.save_to_file(doc_df, kb_path)
#     else:
#         if not os.path.exists(kb_path):
#             doc_df.to_csv(kb_path, encoding='utf-8')
#         else:
#             doc_df.to_csv(kb_path, encoding='utf-8', index=False)
#
#     load_resource(resource, kb_dir)
#     _ = await encode_kb(user, add_dir=kb_dir, mode="add") # kb_dir is the full relative path
#     print('\t know file write successfully...')

# def load_resource(resource, kb_dir):
#     for link, data in resource.items():
#         if link.startswith('TABLE_'):
#             tb_record = {}
#             tb_record_pth = os.path.join(kb_dir, 'table_record.json')
#             if os.path.exists(tb_record_pth):
#                 if encryptor.encrypt:
#                     tb_record = encryptor.load_from_file(tb_record_pth)
#                 else:
#                     with open(tb_record_pth, 'r', encoding='utf-8') as f:
#                         tb_record = json.load(f)
#             tb_df = data['data']
#             if link in tb_record:
#                 tb_name = tb_record[link]
#             else:
#                 tb_name = data['name']
#                 tb_record.update({link : tb_name})
#                 if encryptor.encrypt:
#                     encryptor.save_to_file(tb_record, tb_record_pth)
#                 else:
#                     with open(tb_record_pth, 'w', encoding='utf-8') as f:
#                         json.dump(tb_record, f, ensure_ascii=False, indent=4)
#
#             tb_path = os.path.join(kb_dir, tb_name)
#             # tbl_html = data['data']
#             # tb_df = pd.read_html(StringIO(tbl_html))[0]
#             if encryptor.encrypt:
#                 encryptor.save_to_file(tb_df, tb_path)
#             else:
#                 tb_df.to_csv(tb_path, encoding='utf-8', index=False)
#
#         elif link.startswith('IMAGE_'):
#             img_record = {}
#             img_record_pth = os.path.join(kb_dir, 'image_record.json')
#             if os.path.exists(img_record_pth):
#                 if encryptor.encrypt:
#                     img_record = encryptor.load_from_file(img_record_pth)
#                 else:
#                     with open(img_record_pth, 'r', encoding='utf-8') as f:
#                         img_record = json.load(f)
#
#             img_base64 = data['data'].split(',')[-1]
#             if link in img_record:
#                 image_name = img_record[link]
#             else:
#                 image_name = data['name']
#                 img_record.update({link : image_name})
#                 if encryptor.encrypt:
#                     encryptor.save_to_file(img_record, img_record_pth)
#                 else:
#                     with open(img_record_pth, 'w', encoding='utf-8') as f:
#                         json.dump(img_record, f, ensure_ascii=False, indent=4)
#
#             image_output_path = os.path.join(kb_dir, image_name)
#             img_bin = base64.b64decode(img_base64)
#             if encryptor.encrypt:
#                 encryptor.save_to_file(img_bin, image_output_path)
#             else:
#                 with open(image_output_path, 'wb') as image_file:
#                     image_file.write(img_bin)

# detail = []
# data_types = []
# filter_merged_paths = []
# for sim_content_path in merged_paths:
#     contents = all_contents_df[all_contents_df['path'] == sim_content_path]['content'].tolist()
#     if len(contents) == 0:
#         logger.warning('sim_content:{}', sim_content_path)
#         continue
#     all_content = ''.join(contents).replace('__HHF__', '\n')
#     detail.append(all_content)
#
#     if '-->images-->' in sim_content_path:
#         type = 3
#     elif '__摘要总结__' in sim_content_path and sim_content_path.endswith('__包括__'):
#         type = 4
#     else:
#         type = 2
#     data_types.append(type)
#     filter_merged_paths.append(sim_content_path)
#     if len(filter_merged_paths) == topk:
#         break

# def answer_stream_doc(user, user_intention, res4answer, act_marker=None, api_name='qwen_stream_api'):
#     if user.USER_SETTINGS['USE_LOCAL_LLM']:
#         api_name = 'local_stream_api'
#
#     if act_marker=='提问':
#         res = checkerboard_simple_ask(user, user_intention, res4answer, api_name=api_name, isModel=False)
#         if isinstance(res, str):
#             res = f'data: {res}\n\n'
#         yield from res
#
#     if act_marker=='重写':
#         res = rewrite_(res4answer, user.llm_apis[api_name], user.USER_SETTINGS['LOCAL_LLM_NAME'], user.local_llm, user.local_llm_tz, user.llm_histories, user.model_config, task='rewrite-paras')
#         if isinstance(res, str):
#             res = f'data: {res}\n\n'
#         yield from res
#
#     elif act_marker=='缩写':
#         res = rewrite_(res4answer, user.llm_apis[api_name], user.USER_SETTINGS['LOCAL_LLM_NAME'], user.local_llm, user.local_llm_tz, user.llm_histories, user.model_config, task='abridge-paras')
#         if isinstance(res, str):
#             res = f'data: {res}\n\n'
#         yield from res
#
#     elif act_marker=='扩写':
#         res = rewrite_(res4answer, user.llm_apis[api_name], user.USER_SETTINGS['LOCAL_LLM_NAME'], user.local_llm, user.local_llm_tz, user.llm_histories, user.model_config, task='extension-paras')
#         if isinstance(res, str):
#             res = f'data: {res}\n\n'
#         yield from res

# def checkerboard_answer(user, user_intention, sim_contents, gen_doc=False, act_marker=None, api_name='qwen_api',
#                         isModel=False, llm_input_limit=3000, save_session=False, show_image=True, add_paras={}):
#     rewrite_fields = ['words', 'topic', 'avoid_topics', 'type', 'style', 'pages']
#     if user['USER_SETTINGS']['USE_LOCAL_LLM']:  # this function supports local_llm
#         api_name = 'local_api'
#
#     ref_contents, summary_texts, merged_df = checkerboard_integrate_contents(user, user_intention, sim_contents,
#                                                                              save_session, show_image)
#     res4answer = (summary_texts + '\n' + ref_contents).strip()
#
#     if gen_doc and act_marker == '输出':
#         clean_file(user['USER_SETTINGS']['OUT_PATH'],
#                    mode='clean')  # delete the file to avoid caching and duplicated downloads
#         clean_file(user['USER_SETTINGS']['DOC_PATH'], mode='remove')
#         generate_doc_from_txt(user,
#                               merged_df,
#                               user.USER_SETTINGS['DOC_PATH'],
#                               user.USER_SETTINGS['OUT_PATH'],
#                               user.tb_record,
#                               user.img_record,
#                               None,  # font_lst
#                               None,  # tree
#                               user.llm_apis[api_name],
#                               user.local_llm,
#                               user.USER_SETTINGS['LOCAL_LLM_NAME'],
#                               user.local_llm_tz,
#                               llm_histories=user.llm_histories,
#                               model_config=user.model_config,
#                               rewrite_threshold=user.USER_SETTINGS['REWRITE_THRESHOLD']
#                               )
#         return {'reply': res4answer, 'doc_file': 'Res_doc.docx'}  # 'answers':answers, 'txt_file':'Res_text.txt',
#
#     else:
#         if act_marker == '提问':
#             if len(summary_texts) > 0 and len(
#                     res4answer) > llm_input_limit:  # If user chooses summary and the length exceeds the limit, we only use summary
#                 res4answer = summary_texts
#             res_content = checkerboard_simple_ask(user, user_intention, res4answer, api_name=api_name, isModel=isModel)
#             return {'reply': res_content}
#
#         elif act_marker == '重写':
#             res_content = rewrite_(res4answer, user.llm_apis[api_name], user.USER_SETTINGS['LOCAL_LLM_NAME'],
#                                    user.local_llm, user.local_llm_tz, user.llm_histories, user.model_config,
#                                    task='rewrite-paras', add_paras=add_paras, rewrite_fields=rewrite_fields)
#             return {'reply': res_content}
#
#         elif act_marker == '填空':
#             res_content = checkerboard_filling_tb(user, user_intention, res4answer, api_name=api_name)
#             try:
#                 res_content = json.dumps(res_content, ensure_ascii=False)
#             except:
#                 res_content = str(res_content)
#             return {'reply': res_content}
#
#         elif act_marker == '输出':
#             return {'reply': res4answer}
#
#
# def answer_stream(user, user_intention, sim_contents, act=None, api_name='ds_api', isModel=False, llm_input_limit=3000,
#                   save_session=False, show_image=True, stream=False, add_paras={}):
#     rewrite_fields = ['words', 'topic', 'type', 'style', 'pages']
#     if user.USER_SETTINGS['USE_LOCAL_LLM']:
#         api_name = 'local_stream_api'
#
#     ref_contents, summary_texts, _ = checkerboard_integrate_contents(user, user_intention, sim_contents, save_session,
#                                                                      show_image)
#     res4answer = (summary_texts + '\n' + ref_contents).strip()
#
#     if act == '提问':
#         if len(res4answer) > llm_input_limit and len(
#                 summary_texts) > 0:  # currently, if user chooses summary and the length exceeds the limit, we only use summary
#             res4answer = summary_texts
#
#         res = checkerboard_simple_ask(user, user_intention, res4answer, api_name=api_name, isModel=isModel,
#                                       stream=stream)
#         if isinstance(res, str):
#             res = f'data: {res}\n\n'
#         yield from res
#
#     elif act == '重写':
#         res = rewrite_(res4answer, user.llm_apis[api_name], user.USER_SETTINGS['LOCAL_LLM_NAME'], user.local_llm,
#                        user.local_llm_tz, user.llm_histories, user.model_config, task='rewrite-paras',
#                        add_paras=add_paras, rewrite_fields=rewrite_fields)
#         if isinstance(res, str):
#             res = f'data: {res}\n\n'
#         yield from res

# def checkerboard_autofill(user, tree, template_path, filled_contents, filled_ids, filled_markers, api_name='qwen_api',
#                           path_val_pairs=[]):
#     clean_file(user.USER_SETTINGS['OUT_PATH'],
#                mode='clean')  # delete the file to avoid caching and duplicated downloads
#     clean_file(user.USER_SETTINGS['REPORT_PATH'], mode='remove')
#     # USER_SETTINGS['REPORT_PATH'] = os.path.join(TEMP_RES_PATH, 'Report_doc.docx')
#     bottom_level_titles = get_bottom_level_titles(tree)
#
#     if '.doc' in template_path:
#         # 1. create the file
#         # doc_template = Document(template_path)
#         doc_res = Document()
#
#         # 2. write the titles and contents
#         if encryptor.encrypt:
#             match_dfs = encryptor.load_from_file(user.USER_SETTINGS['MATCH_DF'])
#         else:
#             match_dfs = pd.read_csv(user.USER_SETTINGS['MATCH_DF'], encoding='utf-8')
#         match_groups = match_dfs.groupby('intention', sort=False)
#
#         all_titles = flatten_dic_dfs(tree)[1:]
#         for title in all_titles:
#             level = get_node_level(tree, title)
#             doc_res = add_paras(doc_res, [title], level)
#
#             if title in bottom_level_titles:  # improve code logic here, the filled_contents seem not USEFUL
#                 if len(filled_contents) > 0:
#                     content = filled_contents.pop(0)
#                 else:
#                     content = 'NULL'
#
#                 if content == 'NULL':
#                     doc_res = add_paras(doc_res, ['(未找到知识，请补充)'], -1, [{'bold': True, 'hc': True}])
#                 elif title in match_groups.groups.keys():
#                     subgroup = match_groups.get_group(title)
#                     current_df = merge_df(subgroup)
#                     doc_res = process_lines_for_doc(current_df,
#                                                     doc_res,
#                                                     user.KB_PATH,
#                                                     user.tb_record,
#                                                     user.img_record,
#                                                     None,  # font_dic
#                                                     None,  # tree
#                                                     user.llm_apis[api_name],
#                                                     user.local_llm,
#                                                     user.USER_SETTINGS['LOCAL_LLM_NAME'],
#                                                     user.local_llm_tz,
#                                                     llm_histories=user.llm_histories,
#                                                     model_config=user.model_config,
#                                                     rewrite_threshold=99999999)  # user.USER_SETTINGS['REWRITE_THRESHOLD']
#
#         if encryptor.encrypt:
#             binary_stream = io.BytesIO()
#             doc_res.save(binary_stream)
#             binary_stream.seek(0)
#             binary_data = binary_stream.getvalue()
#             encryptor.save_to_file(binary_data, user.USER_SETTINGS['REPORT_PATH'])
#         else:
#             doc_res.save(user.USER_SETTINGS['REPORT_PATH'])
#
#     elif '.xls' in template_path:
#         for path, value in path_val_pairs:
#             keys = path.split('-->')
#             current = tree
#             for key in keys[:-1]:  # Traverse to the second last key
#                 current = current[key]
#             last_key = keys[-1]
#             try:
#                 vals = list(json.loads(value).values())
#             except:
#                 vals = [value]
#             current[last_key] = vals  # Set the value at the last key
#
#         flat_dic = flatten_dict(tree)
#         filled_df = pd.DataFrame(flat_dic)
#         filled_df.columns = pd.MultiIndex.from_tuples(filled_df.columns)
#         filled_df.to_excel(user.USER_SETTINGS['TB_PATH'], encoding='utf-8')
#     else:
#         pass
#     user.clean_file(USER_SETTINGS['MATCH_DF'], mode='clean')

# def checkerboard_reason(user, intention, sim_contents, merged_paths, mode='llm', api_name='gpt_api'):
#     if user.seq_reasoner == None or user.mark_reasoner == None:
#         print('No reasoner loaded')
#         return None, None, None
#
#     # path_contents = [ '-->'.join(path.split(os.sep)[USER_SETTINGS['ROOT_LEN'] : ]) for path in merged_paths ]
#     path_contents = [path.split(os.sep)[-1] for path in merged_paths]
#
#     content_lst_text = ''
#     for i, pc in enumerate(path_contents):
#         content_lst_text = content_lst_text + f"\u3010{i + 1} \u3011 " + pc + '\n'
#
#     try:
#         if mode == 'llm' and not api_name == None:
#             print('\tusing llm to reason...')
#             # 1. selected id reasoner
#             answer, llm_histories = use_llm_api(user.llm_apis[api_name],
#                                                 histories=user.llm_histories,
#                                                 paras={'task': 'reason', 'texts': content_lst_text.strip(),
#                                                        'query': intention},
#                                                 config=user['model_config'])
#
#             if not answer['match']:
#                 matched_id = -1
#             else:
#                 matched_id = int(answer['match']) - 1  # the list index begins at 0
#                 matched_id = max(matched_id, -1)
#                 if matched_id > len(merged_paths) - 1:
#                     matched_id = -1
#             matched_term = merged_paths[matched_id]
#
#             # 2. Under development, act marker reasoner
#             marker_ids = [0, 1, 0]
#             return matched_term, str(matched_id + 1), marker_ids
#
#         elif mode == 'rl':
#             try:
#                 print('\tusing local model to reason...')
#                 user.seq_reasoner.load_checkpoint()
#                 user.seq_reasoner.eval()
#
#                 _, intention_embed = vectorize_texts(intention, client=client)
#                 _, content_embeds = vectorize_texts(path_contents, client=client)
#
#                 content_embeds = content_embeds[np.newaxis, :]
#                 intention_embed = intention_embed.reshape(1, 1, intention_embed.shape[0])
#
#                 intention_embed = np.repeat(intention_embed, user['USER_SETTINGS']['TOP_K'], axis=1)
#                 embeddings = np.concatenate((content_embeds, intention_embed),
#                                             axis=2)  # combine query and existing knowledge
#                 # reason knowledge pieces by local model
#                 seq_embeddings = T.tensor(embeddings).to(user.seq_reasoner.device)
#                 seq_pred_arr = user.seq_reasoner(seq_embeddings)
#                 seq_pred_ids = [int(i) for i in (seq_pred_arr >= 0.5).float().cpu().numpy().flatten()]
#                 # reason action markers by local model
#                 mak_embeddings = T.tensor(embeddings).to(user.mark_reasoner.device)
#                 mak_pred_arr = user.mark_reasoner(mak_embeddings)
#                 mak_pred_ids = [int(i) for i in (mak_pred_arr >= 0.5).float().cpu().numpy().flatten()]
#
#                 seq_return_ids = [str(i + 1) for i, val in enumerate(seq_pred_ids) if val == 1]
#                 seq_return_terms = [path_contents[i] for i, val in enumerate(seq_pred_ids) if val == 1]
#
#                 return seq_return_terms, ','.join(seq_return_ids), mak_pred_ids
#             except Exception as e:
#                 print('local model loading failed... \n', e)
#                 return checkerboard_reason(user, intention, sim_contents, merged_paths, mode='llm')
#         else:
#             pass
#     except Exception as e:
#         logger.exception('checkerboard_reason fail! e:{}', e)
#         return None, None, None

# async def checkerboard_simple_ask(user, intention, texts, api_name=None, max_tokens=None, isModel=True, if_judge=False, stream=False):
#     if max_tokens==None:
#         max_tokens = user['USER_SETTINGS']['LLM_QA_OUT_LIMIT']
#     if if_judge:
#         judge, _ = await use_llm_api(user.llm_apis[api_name],
#                                 histories=user.llm_histories,
#                                 paras={ 'task':'judge-kb',
#                                         'query':intention,
#                                         'texts':texts,
#                                         'local_model_name':user['USER_SETTINGS']['LOCAL_LLM_NAME'],
#                                         'local_model':user.local_llm,
#                                         'local_tz': user.local_llm_tz,
#                                         'use_his':False},
#                                 config=user['model_config'])
#
#         if judge.get('judge', False):
#             print("\t✅ 知识库内存在相关资料...")
#             answer = await talk2kb(user, intention, texts, api_name, max_tokens, stream)
#         else:
#             print(f"\t⚠️ 知识库内暂无相关资料...")
#             if isModel:
#                 answer = await talk2kb(user, intention, texts, api_name, max_tokens, stream)
#                 answer = "****<--知识库中无相关资料，以下为大模型生成答案-->****\n"
#             else:
#                 answer = '****<--知识库中暂无相关资料，我们会持续完善。-->****'
#     else:
#         print("\t⚠️ 未判断知识库资料是否匹配 直接回答...")
#         answer = await talk2kb(user, intention, texts, api_name, max_tokens, stream)
#     return answer
