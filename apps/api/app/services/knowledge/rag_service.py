import os
import uuid
import math
import torch
import matplotlib.pyplot as plt
import numpy as np
from pylab import mpl
from loguru import logger
from app.core.dependencies import get_redis_service
from app.services.redis import RedisService
from app.core.database import get_db_context
from app.core.config import settings
from app.services.ai.prompt_service import build_prompt
from app.services.ai.response_process_service import eval_response
# ARQ依赖已移除，使用Celery替代
from app.services.ai import ai_query_service
import networkx as nx
import torch as T
from rank_bm25 import BM25Okapi
from sentence_transformers import util
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from app.services.common.kb_utils import tokenize2stw_remove, _gc

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


async def gen_sim_matrix(vecs_, self_ids, k=10, use_cosine=True, pre_threshold=0.2, q=0.9):
    if use_cosine:
        norms = np.linalg.norm(vecs_, axis=1, keepdims=True)
        vecs_ = vecs_ / (norms + 1e-10)

    sim_matrix = vecs_ @ vecs_.T # 由于vecs本身ids总是012 所以得到的topids就是dataframe的行号
    n = sim_matrix.shape[0]

    topk_indices = np.zeros((n, k), dtype=int)
    topk_values = np.zeros((n, k))

    for i in range(n):
        sim_matrix[i, i] = -np.inf # 去除自身
        idx = np.argpartition(-sim_matrix[i], k)[:k]
        idx = idx[np.argsort(-sim_matrix[i, idx])] # 再次排序，保证从大到小

        topk_indices[i] = idx
        topk_values[i] = sim_matrix[i, idx]

    threshold = np.max((np.quantile(topk_values, q), pre_threshold))
    filtered_indices = topk_indices.copy() # 拷贝，避免原地修改
    mask = topk_values < threshold
    filtered_indices[mask] = -1

    if len(self_ids) > 0: # 凡是候选属于 self_ids 的置 -1
        invalid_mask = np.isin(filtered_indices, self_ids)
        filtered_indices[invalid_mask] = -1
    return filtered_indices, threshold

async def find_closest(texts, text_vectors, q_vec, topk, msg=None, add_identifiers=None, hybrid=False, stopwords=None, token_corpus=None, threshold=0):
    def find_cutoff(sorted_list, th_):
        if th_<=0:
            return sorted_list[-1], len(sorted_list)
        else:
            for i, number in enumerate(sorted_list):
                if number <= th_:
                    return (sorted_list[i-1], i) if i > 0 else (sorted_list[0], 1)  # Return element and position
            return sorted_list[-1], len(sorted_list)

    q_vec = q_vec.astype('float32')
    text_vectors = text_vectors.astype('float32')
    semantic_scores = util.cos_sim(q_vec, text_vectors)
    semantic_scores = semantic_scores.cpu().detach().numpy().reshape(-1) # list(semantic_scores.detach().numpy().reshape(-1))

    if hybrid:
        msg_tokens = tokenize2stw_remove([msg], stopwords)
        msg_tokens = msg_tokens[-1].split('->')
        bm25 = BM25Okapi(token_corpus)
        kw_scores = bm25.get_scores(msg_tokens)
    else:
        kw_scores = np.zeros((len(texts)), dtype=np.float32)
        
    kw_scores = [math.log(1 + s) for s in kw_scores]
    hybrid_scores = np.array(semantic_scores) + kw_scores
    
    sim_ids = list(np.argsort(hybrid_scores)[::-1])
    hybrid_scores = list(np.sort(hybrid_scores)[::-1])
    cut_score, cut_idx = find_cutoff(hybrid_scores, threshold)
    
    sim_ids = sim_ids[:cut_idx][:topk]
    hybrid_scores = hybrid_scores[:cut_idx][:topk]
    sim_contents = [texts[i] for i in sim_ids][:topk] # sim_contents can be paths or textual contents

    if not add_identifiers is None:
        add_identifiers = [add_identifiers[i] for i in sim_ids][:topk]
    return sim_contents, sim_ids, hybrid_scores, add_identifiers

def merge_paths_soft(zips_pa, zips_con, con_weight=3):
    """
    合并三组路径得分，前一组为主，后两组可以设权重。
    """
    score_dict = {}
    # 添加 paths_path 的得分（原始）
    for path_id, score in zips_pa:
        score_dict[path_id] = score

    # 添加 paths_contents 的加权得分
    if zips_con is not None:
        for path_id, score in zips_con:
            weighted_score = score * con_weight
            if path_id in score_dict:
                score_dict[path_id] += weighted_score
            else:
                score_dict[path_id] = weighted_score

    # 添加 paths_summary 的加权得分
    # if paths_sum is not None and scores_sum is not None:
    #     for path, score in zip(paths_sum, scores_sum):
    #         weighted_score = score * weights[1]
    #         if path in score_dict:
    #             score_dict[path] += weighted_score
    #         else:
    #             score_dict[path] = weighted_score
    sorted_items = sorted(score_dict.items(), key=lambda x: x[1], reverse=True)
    paths_sorted = [item[0] for item in sorted_items]
    scores_sorted = [item[1] for item in sorted_items]
    return paths_sorted, scores_sorted

async def rerank_(rerank_txt, msg, paths4rank, keep_one=False):
    prompt, temperature, top_p, max_tokens = build_prompt("rerank", rerank_txt, msg, paras={"keep_one":keep_one})
    messages = [
        {"role": "system", "content": "你是一个有帮助的助手"},
        {"role": "user", "content": prompt}
    ]

    ctx_task_id = str(uuid.uuid4())
    
    # 使用Redis直接追踪任务状态，无需数据库持久化
    redis_service = await get_redis_service()
    await redis_service.set(f"task:{ctx_task_id}:status", "processing", ttl=7200)

    # 使用统一的AI查询服务
    rerank_seq = await ai_query_service.query_ai(
        messages=messages,
        user_id=ctx_task_id,
        conversation_id=ctx_task_id,
        timeout=90
    )
    rerank_seq = eval_response(rerank_seq)
    sorted_lst = [paths4rank[i-1] for i in rerank_seq['answer']]
    
    # 更新任务状态为完成
    await redis_service.set(f"task:{ctx_task_id}:status", "complete", ttl=7200)
    return sorted_lst

def vectorize_texts(texts, encoder_=None, use_tensor=False, client=None):
    if encoder_ is not None:
        _gc()
        with torch.no_grad():
            embeddings = encoder_.encode(texts, convert_to_tensor=use_tensor)
        return texts, embeddings

    try:
        embeddings = qwen_embeddings(client, texts)
        return texts, embeddings
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 如果API调用失败，返回零向量
        logger.warning(f"向量化失败，使用零向量替代: {e}")
        import numpy as np
        fallback_dim = getattr(settings, "DEFAULT_EMBEDDING_DIM", 1024)
        zero_embeddings = np.zeros((len(texts), fallback_dim), dtype=np.float32)
        return texts, zero_embeddings

def qwen_embeddings(client, texts, batch_size=None):
    from app.core.constants import ProcessingConstants
    if batch_size is None:
        batch_size = ProcessingConstants.IMG_MAX_TOKENS // 10  # 使用合理的默认值
    all_embeddings = []
    model_name = settings.EMBEDDING_MODEL or "text-embedding-v1"
    deprecated_models = {
        "text-embedding-ada-002": "text-embedding-v1",
        "text-embedding-3-small": "text-embedding-v1",
    }
    if model_name in deprecated_models:
        fallback_model = deprecated_models[model_name]
        logger.warning(
            f"检测到已弃用的嵌入模型 `{model_name}`，自动切换至 `{fallback_model}`"
        )
        model_name = fallback_model
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        completion = client.embeddings.create(
            model=model_name,
            input=batch,
            encoding_format="float"
        )
        embed_res = completion.model_dump()
        embeddings = [item["embedding"] for item in embed_res["data"]]
        all_embeddings.extend(embeddings)
    return np.array(all_embeddings, dtype=np.float32)

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
