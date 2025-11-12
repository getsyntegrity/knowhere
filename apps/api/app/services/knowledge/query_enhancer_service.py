import os
import pickle
from collections import Counter
from math import exp, log2

import jieba
import numpy as np
from app.services.storage.file_encryptor_service import encryptor
from app.utils.llm_utils import use_llm_api
from app.utils.math_utils import min_max_normalize
from app.utils.text_utils import tokenize2stw_remove
from joblib import Parallel, delayed


# Load external corpus
def load_corpus(corpus_dir, cache_file, n_jobs=-1):
    def read_and_tokenize_file(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            return ' '.join(jieba.lcut(content))
    
    def process_category(category_dir):
        tokenized_texts = []
        for file in os.listdir(category_dir):
            file_path = os.path.join(category_dir, file)
            tokenized_texts.append(read_and_tokenize_file(file_path))
        return tokenized_texts

    if os.path.exists(cache_file):
        with open(cache_file, 'rb') as f:
            corpus_data = pickle.load(f)
    else:
        categories = [os.path.join(corpus_dir, d) for d in os.listdir(corpus_dir)]
        all_documents = Parallel(n_jobs=n_jobs)(delayed(process_category)(category) for category in categories)
        corpus_data = [doc for category_docs in all_documents for doc in category_docs]
        
        with open(cache_file, 'wb') as f:
            pickle.dump(corpus_data, f)
    return corpus_data


def compute_entropy(phrase, word_probs, stopwords): # function to compute entropy
    tokens = tokenize2stw_remove([phrase], stopwords)
    entropy = -sum((word_probs.get(token, 1e-6)) * log2(word_probs.get(token, 1e-6)) for token in tokens)
    return entropy


# def compute_joint_probabilities(tokenized_texts): # function to compute joint probabilities
#     word_pairs = defaultdict(int)
#     all_words = ' '.join(tokenized_texts).split()
#     total_pairs = len(all_words) - 1
#     for i in range(total_pairs):
#         pair = (all_words[i], all_words[i + 1])
#         word_pairs[pair] += 1
#     joint_probs = {pair: count / total_pairs for pair, count in word_pairs.items()}
#     return joint_probs


# def compute_mutual_information(phrase1, phrase2, word_probs, joint_probs): # function to compute mutual information
#     tokens1 = jieba_tokenize(phrase1)
#     tokens2 = jieba_tokenize(phrase2)
#     mi = 0.0
#     for t1 in tokens1:
#         for t2 in tokens2:
#             joint_prob = joint_probs.get((t1, t2), 1e-6)
#             prob1 = word_probs.get(t1, 1e-6)
#             prob2 = word_probs.get(t2, 1e-6)
#             mi += joint_prob * log2(joint_prob / (prob1 * prob2))
#     return mi


def compute_corpus_probs_entropys(texts, meta_cache_file): # compute word probabilities based on the corpus
    if os.path.exists(meta_cache_file):
        if encryptor.encrypt:
            corpus_probs_meta = encryptor.load_from_file(meta_cache_file)
        else:
            with open(meta_cache_file, 'rb') as f:
                corpus_probs_meta = pickle.load(f)
    else:
        corpus_probs_meta = {}
        
        maxlen = np.max([len(d) for d in texts])
        minlen = np.min([len(d) for d in texts])
        
        all_words = ' '.join(texts).split()
        total_words = len(all_words)
        word_counts = Counter(all_words)
        
        word_probs = {word: count / total_words for word, count in word_counts.items()}
        print('enter entropy evaluation...')
        entropies = [compute_entropy(t, word_probs) for t in texts]
        
        corpus_probs_meta.update({'word_probs':word_probs,
                                  'corpus_max_len':maxlen, 
                                  'corpus_min_len':minlen, 
                                  'corpus_max_entropy':np.max(entropies), 
                                  'corpus_min_entropy':np.min(entropies)})
        
        if os.path.exists(meta_cache_file):
            encryptor.save_to_file(corpus_probs_meta, meta_cache_file)
        else:
            with open(meta_cache_file, 'wb') as f:
                pickle.dump(corpus_probs_meta, f)
        
    return corpus_probs_meta


def eval_speciality(txt, corpus_probs_meta, alpha=10, right_shift=0.5, epy_clip=2, len_clip=50):
    def sigmoid(x, k=1, x_0=0):
        return 1 / (1 + exp(-k * (x - x_0)))
    
    word_probs = corpus_probs_meta['word_probs']
    max_len = corpus_probs_meta['corpus_max_len']
    min_len = corpus_probs_meta['corpus_min_len']
    max_epy = corpus_probs_meta['corpus_max_entropy']
    min_epy = corpus_probs_meta['corpus_min_entropy']
    
    norm_entropy = compute_entropy(txt, word_probs)
    # norm_entropy = min_max_normalize(entropy, min_epy, min(max_epy, epy_clip))
    norm_len = min_max_normalize(len(txt), min_len, min(max_len, len_clip))
    
    k = 1 + alpha*norm_len
    prob_special = sigmoid(norm_entropy, k, (right_shift-norm_len))
    
    if prob_special>0.5:
        speciality = True
    else:
        speciality = False
    return speciality
    

def divide_queries(query, model_config, USER_SETTINGS, llm_apis, llm_histories, api_name='gpt_api'):
    queries, _ = use_llm_api(llm_apis[api_name],
                                          histories=llm_histories,
                                          paras={'task':'judge-complexity', 
                                                 'query':query,
                                                 'texts':'',
                                                 'domain':'建筑和建造'}, 
                                          config=model_config,
                                          settings=USER_SETTINGS)
    return queries
    

def label_queries(queries, model_config, USER_SETTINGS, llm_apis, llm_histories, api_name='gpt_api'):        
    labelled_queries = []
    purpose_dic = {
            '专业咨询':'询问具体的知识或信息，包括但不限于规范、标准、合同、操作方法等',
            '一般闲聊':'通用的、非专业的、开放性的问题，或者只是想要进行闲聊，例如：“中国的GDP是多少？”、“你好，请问你可以做什么？”等'
        }
        
    corpus_data = load_corpus('../Pretrained models/Corpus', USER_SETTINGS['CORPUS'])
    corpus_probs_meta = compute_corpus_probs_entropys(corpus_data, USER_SETTINGS['CORPUS_META'])
    # joint_probs = compute_joint_probabilities(corpus_data)  
       
    for query in queries:
        labels = []
        if_special = eval_speciality(query, corpus_probs_meta)
        if if_special:
            labels.append('precise')
        else:
            labels.append('fuzzy')        
        
        if not api_name==None:
            purpose, _ = use_llm_api(llm_apis[api_name],
                                                  histories=llm_histories,
                                                  paras={'task':'judge-querypurpose', 
                                                         'query':query, 
                                                         'texts':'',
                                                         'domain':'建筑和建造',
                                                         'purposes': purpose_dic},
                                                  config=model_config,
                                                  settings=USER_SETTINGS)
        else:
            purpose = '专业咨询' # default
            
        if purpose=='专业咨询':
            labels.append('special')
        elif purpose=='一般闲聊':
            labels.append('general')
        else:
            pass
        
        labelled_queries.append(tuple([query]+labels))
    
    return labelled_queries


def judge_history_use():
    # under development, determine history use based on token in the memory, refine history as a local txt
    pass 


def judge_answered():
    # udner development, determine if the retrieved pieces can answer the question
    pass


def judge_action():
    # under development, determine the use mode, find local pieces or traverse the entire space
    # this can be done explicitly, or can use LLM to judge automatically
    pass

    
    
    