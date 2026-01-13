import json
import os
import re
import shutil
import threading
import time
import uuid

import numpy as np
import pandas as pd
from shared.core.config import settings
from shared.core.context import get_current_user
from shared.models.database.user import User
from shared.services.redis import RedisServiceFactory
from shared.services.ai import ai_query_service
from shared.services.ai.prompt_service import build_prompt
from shared.services.ai.response_process_service import eval_response
# ARQ依赖已移除，使用Celery替代
from app.services.common.global_manager_service import (global_df_manager,
                                                        global_dict_manager,
                                                        global_vector_manager)
from app.services.common.kb_utils import (build_tree_from_paths,
                                          clean_contents, gen_str_codes,
                                          split_path_by_node, truncate_paths)
from app.services.document_parser.txt_parser import extract_summary_keywords
from app.services.knowledge.knowledge_base_service import build_sim_matrix
from app.services.knowledge.rag_service import vectorize_texts
from shared.services.storage.file_encryptor_service import encryptor
from loguru import logger
from openai import OpenAI
from tqdm import tqdm

g_lock = threading.Lock()

def check_overlap(node_, user):
    all_contents_df = global_df_manager.get_dataframe(user['user'] + '_all_contents_df')
    if all_contents_df is None: # 很可能说明这是一个新用户
        return False

    exist_ids = all_contents_df[all_contents_df['path'].str.contains(node_, na=False, regex=False)].index.tolist()
    exist_paths = all_contents_df.iloc[exist_ids]['path'].tolist()

    return len(exist_paths)>0
    #****** UNDER DEVELOPMENT 目前是如果要覆盖就先删除再重新加入知识库 否则就跳过

def vec_individual_contents(contents_, cut_len=1024, encoder_=None, client=None):
    if not isinstance(contents_, list):
        contents_ = [contents_]
    content_vecs = np.empty((0, 1024), dtype=np.float32)
    
    try:
        _, content_vecs = vectorize_texts(contents_, encoder_, client=client)
        if content_vecs is None or len(content_vecs) == 0:
            # 如果向量化失败，创建零向量
            content_vecs = np.zeros((len(contents_), 1024), dtype=np.float32)
    except Exception as e:
        logger.warning(f"批量向量化失败，尝试逐个处理: {e}")
        contents_ = [content[:cut_len] for content in contents_]
        for content in contents_:
            try:
                _, vec_ = vectorize_texts(content, encoder_, client=client)
                if vec_ is not None and len(vec_) > 0:
                    content_vecs = np.vstack((content_vecs, vec_))
                else:
                    # 如果单个内容向量化失败，添加零向量
                    zero_vec = np.zeros((1, 1024), dtype=np.float32)
                    content_vecs = np.vstack((content_vecs, zero_vec))
            except Exception as e:
                logger.debug(f'向量化失败: {e}')
                # 添加零向量作为占位符
                zero_vec = np.zeros((1, 1024), dtype=np.float32)
                content_vecs = np.vstack((content_vecs, zero_vec))
    
    # 确保返回的向量数量与输入内容数量匹配
    if len(content_vecs) != len(contents_):
        logger.warning(f"向量数量不匹配，调整向量数量: {len(content_vecs)} -> {len(contents_)}")
        if len(content_vecs) < len(contents_):
            # 如果向量数量不足，添加零向量
            missing_count = len(contents_) - len(content_vecs)
            zero_vecs = np.zeros((missing_count, 1024), dtype=np.float32)
            content_vecs = np.vstack((content_vecs, zero_vecs))
        else:
            # 如果向量数量过多，截取
            content_vecs = content_vecs[:len(contents_)]
    return content_vecs

def vectorize_contents(added_contents_df, root_len, cut_len=8000, client=None):
    logger.info(f'新增知识节点 {len(added_contents_df)} 条...')

    # 处理路径向量（联合summary）
    split_char = settings.SPLIT_CHAR or ";"
    added_paths = (
        added_contents_df.apply(
            lambda row: str(row["path"]) + (
                split_char + str(row["summary"]) if pd.notna(row["summary"]) else ""),
            axis=1
        ).tolist()
    )

    added_paths = [split_char.join(ap.split(split_char)[root_len:]) for ap in added_paths]
    assert len(added_paths) == len(list(set(added_paths)))
    added_path_vecs = vec_individual_contents(added_paths, client=client)

    # 处理知识内容向量
    added_contents = added_contents_df["content"].tolist()
    added_contents = clean_contents(added_contents)
    added_contents_vecs = vec_individual_contents(added_contents, cut_len, client=client)

    default_dim = getattr(settings, "DEFAULT_EMBEDDING_DIM", 1024)

    if len(added_path_vecs) == 0:
        added_path_vecs = np.empty((0, default_dim), dtype=np.float32)
    else:
        added_path_vecs = np.array(added_path_vecs, dtype=np.float32)
        default_dim = added_path_vecs.shape[1]
    if len(added_contents_vecs) == 0:
        added_contents_vecs = np.empty((0, default_dim), dtype=np.float32)
    else:
        added_contents_vecs = np.array(added_contents_vecs, dtype=np.float32)
        default_dim = added_contents_vecs.shape[1]

    try:
        settings.DEFAULT_EMBEDDING_DIM = default_dim  # type: ignore[attr-defined]
    except Exception:
        pass

    return added_contents_vecs, added_path_vecs

def load_new_data(add_root):
    add_df_path = os.path.join(add_root, "KB_PTXT.csv")
    add_contents_df = pd.read_csv(add_df_path, encoding='utf-8', index_col=False, keep_default_na=False)
    return add_contents_df

def load_existing_kb(USER_SETTINGS):
    """
    加载现有知识库数据
    
    Args:
        USER_SETTINGS: 用户设置字典，包含文件路径
        
    Returns:
        tuple: (all_vec, all_path_vec, all_contents_df)
    """
    kb_vec_path = USER_SETTINGS['KB_VEC_PATH']
    kb_path_vec_path = USER_SETTINGS['KB_PATH_VEC_PATH']
    kb_content_path = USER_SETTINGS['KB_CONTENT_PATH']
    
    logger.debug(f"开始加载知识库文件:")
    logger.debug(f"  - 向量文件: {kb_vec_path}")
    logger.debug(f"  - 路径向量文件: {kb_path_vec_path}")
    logger.debug(f"  - 内容文件: {kb_content_path}")
    
    try:
        # 检查文件是否存在
        missing_files = []
        if not os.path.exists(kb_vec_path):
            missing_files.append(f"向量文件: {kb_vec_path}")
        if not os.path.exists(kb_path_vec_path):
            missing_files.append(f"路径向量文件: {kb_path_vec_path}")
        if not os.path.exists(kb_content_path):
            missing_files.append(f"内容文件: {kb_content_path}")
        
        if missing_files:
            logger.warning(f"知识库文件缺失: {', '.join(missing_files)}")
            logger.info("将创建空的默认数据结构")
            raise FileNotFoundError(f"知识库文件缺失: {', '.join(missing_files)}")
        
        # 加载文件
        all_vec = np.load(kb_vec_path)
        all_path_vec = np.load(kb_path_vec_path)
        all_contents_df = pd.read_csv(kb_content_path, encoding='utf-8', keep_default_na=False)
        
        logger.debug(f"成功加载知识库文件:")
        logger.debug(f"  - 向量维度: {all_vec.shape}")
        logger.debug(f"  - 路径向量维度: {all_path_vec.shape}")
        logger.debug(f"  - 内容数量: {len(all_contents_df)}")
        
    except FileNotFoundError as e:
        logger.warning(f"知识库文件不存在，创建默认结构: {e}")
        # 确保目录存在
        from app.services.user.user_directory_service import UserDirectoryService
        UserDirectoryService.ensure_directory_for_file(kb_vec_path)
        UserDirectoryService.ensure_directory_for_file(kb_path_vec_path)
        UserDirectoryService.ensure_directory_for_file(kb_content_path)
        
        all_df_cols = (settings.ALL_DF_COLS or "path,content,summary,type,addtime").split(",")
        default_dim = getattr(settings, "DEFAULT_EMBEDDING_DIM", 1024)
        all_vec = np.empty((0, default_dim), dtype=np.float32)
        all_path_vec = np.empty((0, default_dim), dtype=np.float32)
        all_contents_df = pd.DataFrame(columns=all_df_cols)
        logger.info(f"创建默认数据结构 - 向量维度: {default_dim}, 列: {all_df_cols}")
        
    except Exception as e:
        logger.error(f"读取现有知识库失败: {e}")
        logger.error(f"错误类型: {type(e).__name__}")
        logger.error(f"尝试加载的文件路径:")
        logger.error(f"  - KB_VEC_PATH: {kb_vec_path}")
        logger.error(f"  - KB_PATH_VEC_PATH: {kb_path_vec_path}")
        logger.error(f"  - KB_CONTENT_PATH: {kb_content_path}")
        
        # 确保目录存在
        from app.services.user.user_directory_service import UserDirectoryService
        UserDirectoryService.ensure_directory_for_file(kb_vec_path)
        UserDirectoryService.ensure_directory_for_file(kb_path_vec_path)
        UserDirectoryService.ensure_directory_for_file(kb_content_path)
        
        # 创建默认结构
        all_df_cols = (settings.ALL_DF_COLS or "path,content,summary,type,addtime").split(",")
        default_dim = getattr(settings, "DEFAULT_EMBEDDING_DIM", 1024)
        all_vec = np.empty((0, default_dim), dtype=np.float32)
        all_path_vec = np.empty((0, default_dim), dtype=np.float32)
        all_contents_df = pd.DataFrame(columns=all_df_cols)
        logger.info(f"创建默认数据结构作为后备方案")
    
    return all_vec, all_path_vec, all_contents_df

def gen_img_tb_records(all_contents_df, resource_pth, kb_pth):
    resource_dic = {}
    pattern = re.compile(r'(TABLE_.*?_TABLE|IMAGE_.*?_IMAGE)')
    resource_df = all_contents_df[
        all_contents_df["type"].astype(str).str.match(pattern)
    ]

    for i, row in resource_df.iterrows():
        description = re.sub(pattern, "", row['content'])
        split_char = settings.SPLIT_CHAR or ";"
        path_ = re.sub(split_char, os.sep, row['path']).replace(f"{kb_pth}{os.sep}", "")
        id_ = row['type']
        resource_dic.update({id_: {"path": path_, "content": description}})

    with open(resource_pth, "w", encoding="utf-8") as f:
        json.dump(resource_dic, f, ensure_ascii=False, indent=4)
    return resource_dic

async def encode_kb(user_info, add_dir=None, filtered_added_df=None, remove_node=None, mode="normal"):
    client = OpenAI(
        api_key=settings.ALI_API_KEY,
        base_url=settings.ALI_URL
    )

    start = time.time()
    USER_SETTINGS = user_info['USER_SETTINGS']
    with g_lock:
        all_vec, all_path_vec, all_contents_df = load_existing_kb(USER_SETTINGS)

    if mode=="add":
        if (filtered_added_df is None) and (add_dir is not None):
            add_contents_df = load_new_data(add_dir)
            all_existing_paths = all_contents_df['path'].tolist()
            filtered_added_df = add_contents_df[~add_contents_df['path'].isin(set(all_existing_paths))].copy()

        if len(filtered_added_df)>0:
            added_vectors, added_path_vecs = vectorize_contents(filtered_added_df, root_len=USER_SETTINGS['ROOT_LEN'], client=client)
            # *******UNDER-DEVELOPMENT****** establish relationships

            # 检查向量化结果是否有效
            if added_vectors is not None and added_path_vecs is not None and len(added_vectors) > 0 and len(added_path_vecs) > 0:
                existing_dim = all_vec.shape[1] if all_vec.size else None
                new_dim = added_vectors.shape[1]
                if existing_dim and existing_dim != new_dim:
                    logger.warning(
                        f"检测到旧向量维度 {existing_dim} 与新向量维度 {new_dim} 不一致，正在重新向量化现有知识库"
                    )
                    if len(all_contents_df) > 0:
                        reencoded_vecs, reencoded_path_vecs = vectorize_contents(
                            all_contents_df,
                            root_len=USER_SETTINGS['ROOT_LEN'],
                            client=client
                        )
                        all_vec = reencoded_vecs
                        all_path_vec = reencoded_path_vecs
                    else:
                        all_vec = np.empty((0, new_dim), dtype=np.float32)
                        all_path_vec = np.empty((0, new_dim), dtype=np.float32)
                with g_lock: # 在已有知识库库内concatenate新知识
                    all_vec = np.vstack((all_vec, added_vectors))
                    all_path_vec = np.vstack((all_path_vec, added_path_vecs))
                    all_contents_df = pd.concat([all_contents_df, filtered_added_df], ignore_index=True)
            else:
                logger.warning("向量化失败，跳过添加新知识到知识库")

    elif mode=="remove" and remove_node is not None:
        all_contents_df, all_vec, all_path_vec = remove_from_kb(user_info, remove_node, all_vec, all_path_vec, all_contents_df)

    assert len(all_contents_df)==len(all_path_vec) and len(all_contents_df)==len(all_vec)
    USER_SETTINGS['EMBEDDING_LEN'] = all_vec.shape[-1]
    if not mode=="normal":
        with g_lock:
            # 确保保存文件的目录存在（修复FileNotFoundError问题）
            from app.services.user.user_directory_service import UserDirectoryService
            UserDirectoryService.ensure_directory_for_file(USER_SETTINGS['KB_VEC_PATH'])
            UserDirectoryService.ensure_directory_for_file(USER_SETTINGS['KB_PATH_VEC_PATH'])
            UserDirectoryService.ensure_directory_for_file(USER_SETTINGS['KB_CONTENT_PATH'])
            
            np.save(USER_SETTINGS['KB_VEC_PATH'], all_vec)
            np.save(USER_SETTINGS['KB_PATH_VEC_PATH'], all_path_vec)
            if encryptor.encrypt:
                encryptor.save_to_file(all_contents_df, USER_SETTINGS['KB_CONTENT_PATH'])
            else:
                all_contents_df.to_csv(USER_SETTINGS['KB_CONTENT_PATH'], encoding='utf-8', index=False)

    user_info['all_contents_df'] = all_contents_df
    user_info['all_vec'] = all_vec
    user_info['all_path_vec'] = all_path_vec
    user_info['resource_dict'] = gen_img_tb_records(all_contents_df, user_info['USER_SETTINGS']['RESOURCE_PATH'], user_info['KB_PATH'])

    global_vector_manager.add_or_update_vector(f"{user_info['user']}_all_contents_vec", user_info['all_vec'])
    global_vector_manager.add_or_update_vector(f"{user_info['user']}_all_path_vec", user_info['all_path_vec'])
    global_df_manager.add_or_update_dataframe(f"{user_info['user']}_all_contents_df", user_info['all_contents_df'])
    global_dict_manager.add_or_update_dict(f"{user_info['user']}_resource_dict", user_info['resource_dict'])
    logger.info('知识库内容向量化完成，花费时间 {} s'.format(np.round((time.time()-start), 3)))
    return user_info

def remove_from_kb(user_info, remove_node, all_vec, all_path_vec, all_contents_df):
    # Step 1: 找出所有包含 remove_node 的行索引
    start = time.time()
    remove_ids = all_contents_df[all_contents_df['path'].str.contains(remove_node, na=False, regex=False)].index.tolist()
    remove_paths = all_contents_df.iloc[remove_ids]['path'].tolist()

    # Step 2: 删除 DataFrame 中的这些行
    all_contents_df.drop(index=remove_ids, inplace=True)
    all_contents_df.reset_index(drop=True, inplace=True)
    # Step 3: 删除对应的向量和路径引用
    all_vec = np.delete(all_vec, remove_ids, axis=0)
    all_path_vec = np.delete(all_path_vec, remove_ids, axis=0)

    # Step 4: 删除实际文件（本地或云端）按知识节点文件夹删除
    real_remove_paths = truncate_paths(remove_paths, remove_node)
    for remove_path in real_remove_paths:
        split_char = settings.SPLIT_CHAR or ";"
        remove_path = os.path.join(*remove_path.split(split_char))
        try:
            if os.path.isfile(remove_path):  # 如果是图表等独立文件
                os.remove(remove_path)
                logger.debug(f"已删除文件: {remove_path}")
            elif os.path.isdir(remove_path):  # 如果是文件夹
                shutil.rmtree(remove_path)  # 删除文件夹及其内容
                logger.debug(f"已删除节点: {remove_path}")
            else:
                continue
        except Exception as e:
            logger.error(f"删除失败 {remove_path}: {e}")

    # Step 6: 重建一些有用的基础文件夹结构
    os.makedirs(user_info['USER_SETTINGS']['TEMP_FILE_PATH'], exist_ok=True)
    os.makedirs(user_info['USER_SETTINGS']['SUPP_FILE_PATH'], exist_ok=True)
    os.makedirs(user_info['USER_SETTINGS']['TEMPLATE_DIR'], exist_ok=True)
    os.makedirs(user_info['USER_SETTINGS']['RAW_IMG_DIR'], exist_ok=True)
    os.makedirs(user_info['USER_SETTINGS']['FRAGMENT_DIR'], exist_ok=True)
    logger.info('删除知识库内容完成，花费时间 {} s'.format(np.round((time.time()-start)/60, 3)))
    return all_contents_df, all_vec, all_path_vec

async def build_forest(source_node=None, k=5, cut_len=2000, threshold=0.8):
    user_context: User | None = get_current_user()
    redis_service = RedisServiceFactory.get_service()
    from shared.services.redis.user_redis_service import UserRedisService
    user_redis_service = UserRedisService(redis_service)
    user = await user_redis_service.get_user_config(str(user_context.id))
    # 载入/定义关系dic
    rel_dic = {
        "相似": {"desc": "描述的主题和内容都基本相同"},
        "冲突": {"desc": "描述的主题和内容相反或存在明显冲突"},
        "顺序": {"desc": "源片段和目标片段存在先后顺序"}
    }

    # 压缩空间(根据分析树形结构关联 以及 关键词共现)
    top_ids, top_contents_df, m = await build_sim_matrix(user, source_node, k, threshold)
    flat_top_ids = top_ids.flatten()

    compare_dfs = pd.DataFrame(
        np.repeat(top_contents_df.values, m, axis=0),
        columns=top_contents_df.columns
    ).reset_index(drop=True)

    # 插入 target_id 到 path 右侧
    path_idx = compare_dfs.columns.get_loc('path')
    compare_dfs.insert(path_idx + 1, 'target_id', flat_top_ids)
    # 去掉无效行
    compare_dfs = compare_dfs[compare_dfs['target_id'] != -1].reset_index(drop=True)

    # 按共现关键词搜寻
    grouped = compare_dfs.groupby('path')
    for _, sub_df in tqdm(grouped, total=len(grouped), desc='自动分析关联关系...'):
        source_row = sub_df.iloc[0] # 因为每个sub_df path列都是一样的 所以可直接取0
        source_path = source_row['path']
        source_content = source_row['content']
        source_summary = source_row['summary']
        if not source_summary.strip():
            source_txt = f"{source_path}\n\n{source_content[:cut_len]}"
        else:
            source_txt = f"{source_path}\n\n{source_summary}"

        for i, row in sub_df.iterrows():
            target_row = top_contents_df.iloc[row['target_id']]
            target_path = target_row['path']
            target_content = target_row['content']
            target_summary = target_row['summary']
            if not target_row['summary'].strip():
                target_txt = f"{target_path}\n\n{target_content[:cut_len]}"
            else:
                target_txt = f"{target_path}\n\n{target_summary}"

            paras = {"source_txt": source_txt, "target_txt": target_txt, "rel_dic": rel_dic}
            prompt, temperature, top_p, max_tokens = build_prompt(task="connect-kb", texts="", query="", paras=paras)
            messages = [
                {"role": "system", "content": "你是一个有帮助的助手"},
                {"role": "user", "content": prompt}
            ]

            ctx_task_id = gen_str_codes((str(uuid.uuid4()) + target_txt))
            
            # 使用Redis直接追踪任务状态，无需数据库持久化
            redis_service = RedisServiceFactory.get_service()
            await redis_service.set(f"task:{ctx_task_id}:status", "processing", ttl=7200)
            
            # 使用统一的AI查询服务
            connect_res = await ai_query_service.query_ai(
                messages=messages,
                user_id=ctx_task_id,
                conversation_id=ctx_task_id,
                timeout=60,
                max_tokens=max_tokens
            )
            answer = eval_response(connect_res)
            
            # 更新任务状态为完成
            await redis_service.set(f"task:{ctx_task_id}:status", "completed", ttl=7200)


async def build_tree(root_node, smart_summary, cut_len=2000, summary_term="包括以下部分"):
    user_context: User | None = get_current_user()
    redis_service = RedisServiceFactory.get_service()
    from shared.services.redis.user_redis_service import UserRedisService
    user_redis_service = UserRedisService(redis_service)
    user = await user_redis_service.get_user_config(str(user_context.id))
    all_contents_df = global_df_manager.get_dataframe(user['user'] + '_all_contents_df')

    base_df = all_contents_df[all_contents_df['path'].str.contains(root_node, na=False, regex=False)]
    base_paths = all_contents_df.iloc[base_df.index.tolist()]['path'].tolist()

    # 根据过滤之后的paths的第一个来确定原始入库时间和kb_dir
    add_time = base_df['addtime'].tolist()[0] if smart_summary else ""
    split_char = settings.SPLIT_CHAR or ";"
    kb_dirs = split_path_by_node(base_paths[0], root_node)[0].split(split_char)
    base_paths = [split_path_by_node(bp, root_node)[1] for bp in base_paths if (not "-->tables-->" in bp) and (not "-->images-->" in bp)]

    tree_lst = []
    summary_df = pd.DataFrame(columns=all_contents_df.columns)
    tree = build_tree_from_paths(base_paths)

    await process_tree_dic(tree, [], tree_lst)
    logger.debug(f"树结构列表: {tree_lst}")

    # bottom-up 处理 tree 递归summary
    tree_lst.sort(key=lambda x: x["label"], reverse=True)
    for i, tree_ in enumerate(tree_lst):
        upper_term = tree_["path"]
        child_keys = tree_["children"]

        upper_summary = f"{upper_term}<--**{summary_term}**-->:\n{chr(10).join(child_keys)}" # 通过 <--** & **--> 定位方便获取children路径
        upper_summary_path = split_char.join((kb_dirs + [upper_term, summary_term]))

        if smart_summary:
            lower_contents = []
            for child_key in child_keys:
                lower_path = split_char.join([p for p in (kb_dirs + [upper_term] + [child_key]) if p])
                lower_df = all_contents_df[all_contents_df['path'] == lower_path] # 处理下层是子叶节点的路径
                if len(lower_df)==0:
                    lower_path = f"{lower_path}{split_char}{summary_term}" # 处理下层不是子叶节点的路径（这些路径已被summary过 路径有变化）
                    lower_df = all_contents_df[all_contents_df['path'] == lower_path]
                if len(lower_df)==0:
                    raise Exception(f"❌ {lower_path} 未匹配到all_contents_df内的路径!")

                count_ = 1
                assert len(lower_df)==1 # 理论上每个路径应该只对对应1行
                for _, row in lower_df.iterrows():
                    lower_summary = row['summary']
                    if not lower_summary.strip(): # 如果下层节点没有summary 就取其content的前一部分
                        lower_summary = row['content'][:cut_len]
                    lower_contents.append(f"下层第{count_}个节点内容\n{lower_summary}\n")
                    count_ += 1

            lower_contents = clean_contents(lower_contents)
            res_ = await extract_summary_keywords("\n".join(lower_contents), summary_len=300)
            upper_summary = f"{upper_summary}\n\n包括的{len(lower_contents)}项内容可归纳为:\n{res_}"

        know_id = gen_str_codes(upper_summary + str(uuid.uuid4()))
        summary_dic = {
            "content": upper_summary,
            "path": upper_summary_path,
            "type": "SUMMARY",
            "length": len(upper_summary),
            "keywords": "",
            "summary": upper_summary,
            "know_id": know_id,
            "tokens": "",
            "connectto": "",
            "addtime": add_time,
        }
        summary_row = pd.DataFrame([summary_dic], columns=all_contents_df.columns)
        summary_df = pd.concat([summary_df, summary_row], ignore_index=True)
        all_contents_df = pd.concat([all_contents_df, summary_row], ignore_index=True) # 更新了这个之后 更上层的递归才会有lower summary的值

    await encode_kb(user, filtered_added_df=summary_df, mode="add")
    return tree_lst

async def process_tree_dic(node_dict, path_prefix, results):
    split_char = settings.SPLIT_CHAR or ";"
    node_result = {}

    for name, sub_dict in node_dict.items():
        path = path_prefix + [name]
        level = len(path) - 1

        if not sub_dict:  # 叶子
            node_result[name] = ""
            continue

        # 非叶子：递归处理子节点
        child_contents = {}
        for child_name, child_subdict in sub_dict.items():
            child_result = await process_tree_dic({child_name: child_subdict}, path, results)
            child_contents.update(child_result)

        # 当前节点 content 只拼接下层的名字
        lower_include = "\n\t".join(child_contents.keys())

        # 记录非叶子节点
        results.append({
            "path": f"{split_char}".join(path),  # 完整路径
            "children": list(child_contents.keys()),  # 只保留名字
            "label": level
        })
        node_result[name] = lower_include
    return node_result


# def gen_bfs_tree(start_path, skip_lst=['Supplementary Files', 'desktop.ini']):
#     bfs_tree = {}
#
#     for root, dirs, files in os.walk(start_path):
#         paths = path_handle(root, 'split')
#
#         intersect_ = intersect_lst(skip_lst, paths)
#         if len(intersect_) > 0:
#             continue
#
#         sub_dict = bfs_tree
#         for folder in paths[1:]:
#             sub_dict = sub_dict.setdefault(folder, {})
#
#         str_path = os.path.join(*paths)
#         if str_path == start_path:
#             continue
#     return bfs_tree
#
#
# def bfs_keys(tree):
#     for key, value in tree.items():
#         if isinstance(value, dict):
#             value = bfs_keys(value)  # Recurse into sub-dictionaries
#             key, embedding = vectorize_texts(key)
#             tree[key] = {"embedding": embedding, "sub_tree": value}
#     return tree
#
#
# def draw_path(tree, path, file_suffixes, paths):
#     file_suffixes = tuple(file_suffixes)
#     for key in tree:
#         new_path = path + (key,)
#         if isinstance(tree[key], dict) and tree[key]:  # check if this is a directory
#             draw_path(tree[key], new_path, file_suffixes, paths)
#         elif key.endswith(file_suffixes):
#             paths.append(new_path)
#     return paths
#
#
# def form_path_tree(start_path, skip_lst=['Supplementary Files', 'desktop.ini']):
#     know_tree = {}
#     for root, dirs, files in os.walk(start_path):
#         paths = path_handle(root, 'split')
#
#         intersect_ = intersect_lst(skip_lst, paths)
#         if len(intersect_) > 0:
#             continue
#
#         sub_dict = know_tree
#         for folder in paths[1:]:
#             sub_dict = sub_dict.setdefault(folder, {})
#
#         str_path = os.path.join(*paths)
#         if str_path == start_path:
#             continue
#
#         for file in files:
#             sub_dict.setdefault(file, {})
#     return know_tree

# def check_progress(add_filename, add_dir):
#     if add_filename:
#         sql = 'select 1 from import_progress where file_name=? and dir_path=? limit 1'
#         exist_file = SqliteDB().selectone(sql, (add_filename, add_dir))
#         if not exist_file:
#             added_contents = []
#             added_vectors = np.empty((0, 1024), dtype=np.float32)
#             added_paths = []
#             added_path_vecs = np.empty((0, 1024), dtype=np.float32)
#             added_types = []
#             added_lengths = []
#             added_record_path_ref = {}
#             added_tokens = []
#             added_keywords= []
#             added_summaries = []
#             added_knowids = []
#
#             added_df = pd.DataFrame({'content':added_contents,
#                                     'path':added_paths,
#                                     'type':added_types,
#                                     'length':added_lengths,
#                                     'keywords':added_keywords,
#                                     'summary':added_summaries,
#                                     'know_id':added_knowids,
#                                     'tokens':added_tokens})
#             return False, added_df, added_vectors, added_path_vecs, added_record_path_ref
#         # sql = 'update import_progress set progress=?, end_time=? where file_name=? and dir_path=?'
#         # SqliteDB().update(sql, ("000", datetime.now(), add_filename, add_dir))
#     return True, None, None, None, None

# def get_dir_path(fragment_path, KB_PATH):
#     i = 0
#     real_file_dir = ''
#     fragment_paths = fragment_path.split(SPLIT_CHAR)
#     for path in fragment_paths:
#         temp_path = os.path.join(real_file_dir, path)
#         if not os.path.isdir(os.path.join(KB_PATH, temp_path)):
#             break
#         real_file_dir = temp_path
#         i += 1
#
#     file_dir = f'{SPLIT_CHAR}'.join(fragment_paths[:i])
#     sub_path = f'{SPLIT_CHAR}'.join(fragment_paths[i:])
#     return os.path.join(KB_PATH, real_file_dir), file_dir, sub_path

# def process_pathvec(system_path, path_item, added_path_vecs, record_path_ref, stopwords=None, encoder_=None):
#     # def assign_path_weights(n, mode='normal'):
#     #     if mode=='normal':
#     #         weights = np.ones(n)
#     #     else:
#     #         indices = np.linspace(-1, 1, n)
#     #         weights = 1 - (indices**2)
#     #         weights = 0.5 * weights + 0.5
#     #     return weights.tolist()
#
#     # path_item = '-->'.join([part for i, part in enumerate(path_item.split('-->')) if i not in [0, 2]]) # only for developing WIKI data
#     if stopwords is None:
#         stopwords = []
#     path_its = path_item.split(settings.SPLIT_CHAR)
#     _, path_vec = vectorize_texts(path_item, encoder_)
#     try:
#         added_path_vecs.append(path_vec)
#     except:
#         added_path_vecs = np.vstack((added_path_vecs, path_vec))
#
#     path_item = unify_key(path_item, record_path_ref)
#     path_desc = tokenize2stw_remove(path_its, stopwords)
#     record_path_ref.update({path_item: {'system_path': system_path, 'tokens': '->'.join(path_desc)}})
#     return added_path_vecs, record_path_ref
