import math
import traceback
import uuid

import matplotlib.pyplot as plt
import numpy as np
import torch
from shared.core.config import settings
from shared.services.redis import RedisServiceFactory
# ARQ依赖已移除，使用Celery替代
from shared.services.ai import ai_query_service
from shared.services.ai.prompt_service import build_prompt
from shared.services.ai.response_process_service import eval_response
from shared.utils.gc_utils import gc_collect as _gc
from shared.utils.text_utils import tokenize2stw_remove
from loguru import logger
from pylab import mpl
from rank_bm25 import BM25Okapi
from sentence_transformers import util

plt.rcParams['font.sans-serif'] = 'SimHei'
mpl.rcParams['font.sans-serif'] = ['SimHei']
mpl.rcParams['axes.unicode_minus']=False


# def add_files_to_tree(tree, root_path, record_level, current_level=1):
#     # root = path_handle(root_path, 'split')[0] + '/'
#     for key, value in tree.items():
#         current_path = os.path.join(root_path, key)
#         if os.path.isdir(current_path):
#             if current_level >= record_level:  # Only add files if level is 3 or greater
#                 for file in os.listdir(current_path):
#                     if os.path.isfile(os.path.join(current_path, file)):
#                         value[file] = {}
#             # Recurse into sub-directories even if we're not adding files yet
#             add_files_to_tree(value, current_path, record_level, current_level+1)

# def bfs_level_searching(inten_lst, level_nodes, TOP_K, client=None):
#     level_vecs = np.array([v['embedding'] for k, v in level_nodes.items()])
#     level_keys = [k for k in level_nodes.keys()]
#
#     nodes2keep = []
#     intention, q_vector = vectorize_texts(inten_lst, client=client)
#     sim_contents, ids_, similarities, _ = find_closest(level_keys, level_vecs, q_vector, TOP_K)
#     # print(level_keys, ' ', similarities)
#
#     nodes2keep.extend(sim_contents)
#     nodes2keep = list(set(nodes2keep))
#     return nodes2keep

# def bfs_filtering(inten_lst, tree, TOP_K, tokenizer, model):
#     cut_bfs_tree = {}
#     level_nodes = {k: v for k, v in tree.items() if isinstance(v, dict) and 'sub_tree' in v}
#     nodes2keep = bfs_level_searching(inten_lst, level_nodes, TOP_K, tokenizer, model)
#     print('bfs selected nodes: ', nodes2keep)
#     for key in nodes2keep:
#         value = tree[key]
#         if isinstance(value['sub_tree'], dict) and not value['sub_tree']=={}:
#             value['sub_tree'] = bfs_filtering(inten_lst, value['sub_tree'], TOP_K, tokenizer, model)
#         cut_bfs_tree[key] = value
#     return cut_bfs_tree

# def bfs_reverse(tree):
#     inversed_tree = {}
#     for key, value in tree.items():
#         if 'sub_tree' in value and isinstance(value['sub_tree'], dict):
#             value['sub_tree'] = bfs_reverse(value['sub_tree'])
#         inversed_tree[key] = value['sub_tree']
#     return inversed_tree

# def detect_file_type(path_):
#     def detect_(path_, extensions):
#         _, extension = os.path.splitext(path_)
#         return extension.lower() in extensions
#
#     res_type = ''
#     extension_dic = {
#         'table' : ['.csv', '.xls', '.xlsx']
#         # add other type and lists
#         }
#
#     for ex_key, extensions in extension_dic.items():
#         bool_ = detect_(path_, extensions)
#         if bool_==True:
#             res_type = ex_key
#             break
#     return res_type


async def find_closest(texts, text_vectors, q_vec, topk, msg=None, add_identifiers=None, hybrid=False, stopwords=None, token_corpus=None, threshold=0):
    logger.debug(f"开始相似度搜索，文本数量: {len(texts)}, topk: {topk}, 混合模式: {hybrid}")
    logger.debug(f"查询向量形状: {q_vec.shape if hasattr(q_vec, 'shape') else 'unknown'}")
    logger.debug(f"文本向量形状: {text_vectors.shape if hasattr(text_vectors, 'shape') else 'unknown'}")
    
    def find_cutoff(sorted_list, th_):
        if th_<=0:
            return sorted_list[-1], len(sorted_list)
        else:
            for i, number in enumerate(sorted_list):
                if number <= th_:
                    return (sorted_list[i-1], i) if i > 0 else (sorted_list[0], 1)  # Return element and position
            return sorted_list[-1], len(sorted_list)

    try:
        q_vec = q_vec.astype('float32')
        text_vectors = text_vectors.astype('float32')
        logger.debug("开始计算语义相似度")
        semantic_scores = util.cos_sim(q_vec, text_vectors)
        semantic_scores = semantic_scores.cpu().detach().numpy().reshape(-1)
        logger.debug(f"语义相似度计算完成，分数范围: [{semantic_scores.min():.4f}, {semantic_scores.max():.4f}]")

        if hybrid:
            logger.debug("使用混合搜索模式，计算关键词分数")
            msg_tokens = tokenize2stw_remove([msg], stopwords)
            msg_tokens = msg_tokens[-1].split('->')
            logger.debug(f"提取的关键词: {msg_tokens}")
            bm25 = BM25Okapi(token_corpus)
            kw_scores = bm25.get_scores(msg_tokens)
            logger.debug(f"关键词分数范围: [{kw_scores.min():.4f}, {kw_scores.max():.4f}]")
        else:
            logger.debug("使用纯语义搜索模式")
            kw_scores = np.zeros((len(texts)), dtype=np.float32)
            
        kw_scores = [math.log(1 + s) for s in kw_scores]
        hybrid_scores = np.array(semantic_scores) + kw_scores
        logger.debug(f"混合分数计算完成，分数范围: [{hybrid_scores.min():.4f}, {hybrid_scores.max():.4f}]")
        
        sim_ids = list(np.argsort(hybrid_scores)[::-1])
        hybrid_scores = list(np.sort(hybrid_scores)[::-1])
        cut_score, cut_idx = find_cutoff(hybrid_scores, threshold)
        logger.debug(f"阈值过滤完成，截断分数: {cut_score:.4f}, 截断位置: {cut_idx}")
        
        sim_ids = sim_ids[:cut_idx][:topk]
        hybrid_scores = hybrid_scores[:cut_idx][:topk]
        sim_contents = [texts[i] for i in sim_ids][:topk]
        logger.debug(f"最终返回 {len(sim_contents)} 个相似内容")

        if not add_identifiers is None:
            add_identifiers = [add_identifiers[i] for i in sim_ids][:topk]
            logger.debug(f"返回 {len(add_identifiers)} 个标识符")
        
        return sim_contents, sim_ids, hybrid_scores, add_identifiers
        
    except Exception as e:
        logger.error(f"相似度搜索过程中发生异常: {str(e)}")
        logger.error(f"异常类型: {type(e).__name__}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise e

def merge_paths_soft(zips_pa, zips_con, con_weight=3):
    """
    合并三组路径得分，前一组为主，后两组可以设权重。
    """
    logger.debug(f"开始合并路径得分，路径得分数量: {len(zips_pa)}, 内容得分数量: {len(zips_con) if zips_con else 0}")
    logger.debug(f"内容权重: {con_weight}")
    
    try:
        score_dict = {}
        # 添加 paths_path 的得分（原始）
        logger.debug("添加路径得分")
        for path_id, score in zips_pa:
            score_dict[path_id] = score
        logger.debug(f"添加了 {len(zips_pa)} 个路径得分")

        # 添加 paths_contents 的加权得分
        if zips_con is not None:
            logger.debug("添加内容加权得分")
            for path_id, score in zips_con:
                weighted_score = score * con_weight
                if path_id in score_dict:
                    score_dict[path_id] += weighted_score
                    logger.debug(f"路径 {path_id} 得分更新: {score_dict[path_id] - weighted_score:.4f} -> {score_dict[path_id]:.4f}")
                else:
                    score_dict[path_id] = weighted_score
            logger.debug(f"添加了 {len(zips_con)} 个内容得分")
        else:
            logger.debug("无内容得分需要添加")

        # 添加 paths_summary 的加权得分
        # if paths_sum is not None and scores_sum is not None:
        #     for path, score in zip(paths_sum, scores_sum):
        #         weighted_score = score * weights[1]
        #         if path in score_dict:
        #             score_dict[path] += weighted_score
        #         else:
        #             score_dict[path] = weighted_score
        
        logger.debug(f"开始排序，总路径数: {len(score_dict)}")
        sorted_items = sorted(score_dict.items(), key=lambda x: x[1], reverse=True)
        paths_sorted = [item[0] for item in sorted_items]
        scores_sorted = [item[1] for item in sorted_items]
        
        logger.debug(f"路径合并完成，返回 {len(paths_sorted)} 个排序后的路径")
        logger.debug(f"得分范围: [{min(scores_sorted):.4f}, {max(scores_sorted):.4f}]")
        return paths_sorted, scores_sorted
        
    except Exception as e:
        logger.error(f"合并路径得分过程中发生异常: {str(e)}")
        logger.error(f"异常类型: {type(e).__name__}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise e

async def rerank_(rerank_txt, msg, paths4rank, keep_one=False):
    logger.debug(f"开始重新排序，路径数量: {len(paths4rank)}, 保留一个: {keep_one}")
    logger.debug(f"重新排序文本: {rerank_txt[:100]}..." if len(rerank_txt) > 100 else rerank_txt)
    logger.debug(f"查询消息: {msg[:100]}..." if len(msg) > 100 else msg)
    
    try:
        prompt, temperature, top_p, max_tokens = build_prompt("rerank", rerank_txt, msg, paras={"keep_one":keep_one})
        logger.debug(f"构建提示词完成，温度: {temperature}, top_p: {top_p}, max_tokens: {max_tokens}")
        
        messages = [
            {"role": "system", "content": "你是一个有帮助的助手"},
            {"role": "user", "content": prompt}
        ]

        ctx_task_id = str(uuid.uuid4())
        logger.debug(f"生成任务ID: {ctx_task_id}")
        
        # 使用Redis直接追踪任务状态，无需数据库持久化
        redis_service = RedisServiceFactory.get_service()
        await redis_service.set(f"task:{ctx_task_id}:status", "processing", ttl=7200)
        logger.debug("任务状态已设置为处理中")

        # 使用统一的AI查询服务
        logger.debug("开始AI查询服务调用")
        rerank_seq = await ai_query_service.query_ai(
            messages=messages,
            user_id=ctx_task_id,
            conversation_id=ctx_task_id,
            timeout=90
        )
        logger.debug(f"AI查询服务返回结果: {str(rerank_seq)[:200]}...")
        
        rerank_seq = eval_response(rerank_seq)
        logger.debug(f"解析后的响应: {rerank_seq}")
        
        sorted_lst = [paths4rank[i-1] for i in rerank_seq['answer']]
        logger.debug(f"重新排序完成，返回 {len(sorted_lst)} 个路径")
        
        # 更新任务状态为完成
        await redis_service.set(f"task:{ctx_task_id}:status", "complete", ttl=7200)
        logger.debug("任务状态已更新为完成")
        return sorted_lst
        
    except Exception as e:
        logger.error(f"重新排序过程中发生异常: {str(e)}")
        logger.error(f"异常类型: {type(e).__name__}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise e

def vectorize_texts(texts, encoder_=None, use_tensor=False, client=None):
    logger.debug(f"开始向量化处理，文本数量: {len(texts) if texts else 0}")
    logger.debug(f"使用编码器: {encoder_ is not None}, 使用张量: {use_tensor}, 客户端: {client is not None}")
    
    if encoder_ is not None:
        logger.debug("使用本地编码器进行向量化")
        _gc()
        with torch.no_grad():
            embeddings = encoder_.encode(texts, convert_to_tensor=use_tensor)
        logger.debug(f"本地编码器向量化完成，向量维度: {embeddings.shape if hasattr(embeddings, 'shape') else 'unknown'}")
        return texts, embeddings

    try:
        logger.debug("使用Qwen API进行向量化")
        embeddings = qwen_embeddings(client, texts)
        logger.debug(f"Qwen API向量化完成，向量维度: {embeddings.shape if hasattr(embeddings, 'shape') else 'unknown'}")
        return texts, embeddings
    except Exception as e:
        logger.error(f"向量化过程中发生异常: {str(e)}")
        logger.error(f"异常类型: {type(e).__name__}")
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        logger.warning(f"向量化失败，使用零向量替代: {e}")
        
        fallback_dim = getattr(settings, "DEFAULT_EMBEDDING_DIM", 1024)
        logger.debug(f"使用备用向量维度: {fallback_dim}")
        zero_embeddings = np.zeros((len(texts), fallback_dim), dtype=np.float32)
        logger.warning(f"已生成零向量矩阵，形状: {zero_embeddings.shape}")
        return texts, zero_embeddings

def qwen_embeddings(client, texts, batch_size=10):
    logger.debug(f"开始Qwen向量化，文本数量: {len(texts)}, 批次大小: {batch_size}")
    logger.debug(f"嵌入模型: {getattr(settings, 'EMBEDDING_MODEL', 'unknown')}")
    
    # 参数验证
    if batch_size is None:
        logger.error("batch_size参数为None，使用默认值10")
        batch_size = 10
    
    if not isinstance(batch_size, int) or batch_size <= 0:
        logger.error(f"无效的batch_size: {batch_size}，使用默认值10")
        batch_size = 10
    
    if not texts or len(texts) == 0:
        logger.warning("输入文本列表为空")
        return np.array([], dtype=np.float32)
    
    if client is None:
        logger.error("Qwen客户端为None，无法进行向量化")
        raise ValueError("Qwen客户端未初始化")
    
    all_embeddings = []
    total_batches = math.ceil(len(texts) / batch_size)
    logger.debug(f"将处理 {total_batches} 个批次")
    
    for i in range(0, len(texts), batch_size):
        batch_num = i // batch_size + 1
        batch = texts[i:i + batch_size]
        logger.debug(f"处理第 {batch_num}/{total_batches} 批次，包含 {len(batch)} 个文本")
        
        try:
            completion = client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=batch,
                encoding_format="float"
            )
            embed_res = completion.model_dump()
            embeddings = [item["embedding"] for item in embed_res["data"]]
            all_embeddings.extend(embeddings)
            logger.debug(f"第 {batch_num} 批次处理成功，获得 {len(embeddings)} 个向量")
        except Exception as e:
            logger.error(f"第 {batch_num} 批次处理失败: {str(e)}")
            logger.error(f"批次内容预览: {batch[:2] if len(batch) > 2 else batch}")
            raise e
    
    result = np.array(all_embeddings, dtype=np.float32)
    logger.debug(f"Qwen向量化完成，总向量数: {len(result)}, 向量维度: {result.shape[1] if len(result) > 0 else 0}")
    return result

    # req_body = {'query': texts}
    # msg, status_code = post_request('http://218.17.187.47:35010/toembedding', req_body)
    # if status_code != 200:
    #     raise ConnectionError(msg)
    # embeddings = np.array(msg['embedding'], dtype=np.float32)
    # return texts, embeddings


# async def find_by_content_voting(msg, q_vector, all_contents_df, all_vec, topk, hybrid=False, stopwords=None, token_corpus=None):
#     all_contents = all_contents_df['content'].tolist()
#     all_paths = all_contents_df['path'].tolist()
#     sim_contents, sim_ids, similarities, sim_paths = await find_closest(all_contents, all_vec, q_vector, topk, msg=msg, add_identifiers=all_paths, hybrid=hybrid, stopwords=stopwords, token_corpus=token_corpus)
#     return sim_paths, sim_contents, similarities
#
#     sim_df = pd.DataFrame({'content':sim_contents, 'sim_id':sim_ids, 'similarity':similarities, 'path':sim_paths})
#     group_res = dict(tuple(sim_df.groupby('path')))
#     group_vote_dic = dict()
#
#     avg_threshold = np.mean(similarities)
#     for gid, sub_df in group_res.items():
#         vote = voting(sub_df, avg_threshold, mode)
#         group_vote_dic.update({gid:vote})
#
#     sorted_group_paths = sorted(group_vote_dic, key=lambda k:group_vote_dic[k], reverse=True)
#     sorted_group_paths = sorted_group_paths[ : topk]
#     return sorted_group_paths

# def voting(df, avg_threshold, mode='normal'):
#     similarities = np.array(df['similarity'].values)
#     differences = similarities - avg_threshold
#
#     if mode=='normal':
#         votes = differences
#     elif mode=='relu':
#         votes = np.maximum(0, differences)
#     elif mode=='exp':
#         votes = np.where(differences > 0, np.exp(differences), differences)
#     else:
#         pass
#     vote = np.sum(votes)
#     return vote

# def merge_paths_soft(*lists, lst_weights=None, nonexist_panelty=False):
#     final_weights = {}
#     for i, lst in enumerate(lists):
#         for idx, elem in enumerate(lst):
#             weight = (len(lst) - idx) * lst_weights[i]
#             final_weights[elem] = final_weights.get(elem, 0) + weight
#
#     if nonexist_panelty==True:
#         all_elems = set().union(*lists)
#         for elem in all_elems:
#             if elem not in final_weights:
#                 final_weights[elem] = -1
#     # sort results by weights
#     merged_paths = sorted(final_weights, key=lambda k:final_weights[k], reverse=True)
#     return merged_paths

# def local_graph(root_node, nodes, show_root=False, **kwargs):
#     G = nx.DiGraph()
#     edge_labels = {}
#     nodes = [ str(nodes.index(node) + 1) +' '  + node.split('.')[0] for node in nodes ]
#     if show_root:
#         G.add_node(root_node)
#         edge_name = kwargs['edge_name']
#
#     # draw tree
#     for n, node in enumerate(nodes):
#         G.add_node(node)
#         if show_root:
#             G.add_edge(root_node, node)
#             edge_labels.update( { (root_node, node) : edge_name } )
#
#     # draw chain
#     edge_name = kwargs['link_name']
#     for i in range(len(nodes) - 1):
#         G.add_edge(nodes[i], nodes[i+1])
#         edge_labels.update({(nodes[i], nodes[i+1]) : edge_name})
#
#     if show_root:
#         sizes = [1200] + [800] * len(nodes)
#     else:
#         sizes = [800] * len(nodes)
#
#     colors = plt.cm.Pastel2(np.linspace(0, 1, G.number_of_nodes()))
#     pos = nx.spring_layout(G)
#     nx.draw(G, pos, with_labels=True, node_color=colors, node_size=sizes)
#     nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)
#     plt.show()
#     return G
