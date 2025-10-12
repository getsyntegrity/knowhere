import fnmatch
import logging
import os
import json
import pandas as pd
import random
from pathlib import Path
import numpy as np
from transformers import AutoConfig, AutoTokenizer
from transformers import (HfArgumentParser, set_seed)
from app.kbs.finetune_encoder.arguments import ModelArguments, DataArguments, RetrieverTrainingArguments as TrainingArguments
from app.kbs.finetune_encoder.data import TrainDatasetForEmbedding, EmbedCollator
from app.kbs.finetune_encoder.modeling import BiEncoderModel
from app.kbs.finetune_encoder.trainer import BiTrainer
from app.kbs.finetune_encoder.LM_Cocktail import mix_models, mix_models_with_data
from app.services.common.kb_utils import extract_know, process_path_texts, use_llm_api


class EncoderFinetuner():
    def __init__(self, USER_SETTINGS, source='interactions', mode='use content'):
        self.parser = HfArgumentParser((ModelArguments, DataArguments, TrainingArguments))
        self.model_args, self.data_args, self.training_args = self.parser.parse_args_into_dataclasses(args=[])
        self.model_args: ModelArguments
        self.data_args: DataArguments
        self.training_args: TrainingArguments
        
        self.model_args.model_name_or_path =os.path.join(USER_SETTINGS['LOCAL_MODELS_DIR'], USER_SETTINGS['LOCAL_ENCODER'])
        if source=='queries': # finetune with generated (simulated) queries
            self.data_args.train_data = USER_SETTINGS['TRAIN_DATA_GEN_QUERIES']
        elif source=='contents': # finetune with contents (un-supervised)
            self.data_args.train_data = USER_SETTINGS['TRAIN_DATA_ALL_CONTENTS']
        elif source=='interactions':
            if mode=='use path':
                self.data_args.train_data = USER_SETTINGS['TRAIN_DATA_PATH']
            if mode=='use content':
                self.data_args.train_data = USER_SETTINGS['TRAIN_DATA_CONTENT']
            else:
                self.data_args.train_data = USER_SETTINGS['TRAIN_DATA_BOTH']
        
        print(self.data_args.train_data)
        self.data_args.passage_max_len = 512
        self.data_args.query_max_len = 128
        
        self.training_args.per_device_train_batch_size = 16
        self.training_args.output_dir = os.path.join(USER_SETTINGS['LOCAL_MODELS_DIR'], USER_SETTINGS['LOCAL_ENCODER'], 'finetuned')
        
        self.training_args.fp16 = True
        self.training_args.learning_rate = 1e-5
        self.training_args.num_epochs = 3
        self.training_args.gradient_checkpointing = True
        self.training_args.deep_speed = './ds_config.json'
        self.training_args.overwrite_output_dir = True
        
        # if (
        #         os.path.exists(self.training_args.output_dir)
        #         and os.listdir(self.training_args.output_dir)
        #         and self.training_args.do_train
        #         and not self.training_args.overwrite_output_dir
        # ):
        #     raise ValueError(
        #         f"Output directory ({self.training_args.output_dir}) already exists and is not empty. Use --overwrite_output_dir to overcome."
        # )
    
    def model_setting(self):
        self.logger = logging.getLogger(__name__)
        
        logging.basicConfig(
            format="%(asctime)s - %(levelname)s - %(name)s -   %(message)s",
            datefmt="%m/%d/%Y %H:%M:%S",
            level=logging.INFO if self.training_args.local_rank in [-1, 0] else logging.WARN,
        )
        self.logger.warning(
            "Process rank: %s, device: %s, n_gpu: %s, distributed training: %s, 16-bits training: %s",
            self.training_args.local_rank,
            self.training_args.device,
            self.training_args.n_gpu,
            bool(self.training_args.local_rank != -1),
            self.training_args.fp16,
        )
        self.logger.info("Training/evaluation parameters %s", self.training_args)
        self.logger.info("Model parameters %s", self.model_args)
        self.logger.info("Data parameters %s", self.data_args)
    
        # Set seed
        set_seed(self.training_args.seed)
    
        num_labels = 1
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_args.tokenizer_name if self.model_args.tokenizer_name else self.model_args.model_name_or_path,
            cache_dir=self.model_args.cache_dir,
            use_fast=False,
        )
        
        config = AutoConfig.from_pretrained(
            self.model_args.config_name if self.model_args.config_name else self.model_args.model_name_or_path,
            num_labels=num_labels,
            cache_dir=self.model_args.cache_dir,
        )

        self.model = BiEncoderModel(model_name=self.model_args.model_name_or_path,
                               normlized=self.training_args.normlized,
                               sentence_pooling_method=self.training_args.sentence_pooling_method,
                               negatives_cross_device=self.training_args.negatives_cross_device,
                               temperature=self.training_args.temperature,
                               use_inbatch_neg=self.training_args.use_inbatch_neg,
                               )
    
        self.logger.info('Config: %s', config)
        if self.training_args.fix_position_embedding:
            for k, v in self.model.named_parameters():
                if "position_embeddings" in k:
                    logging.info(f"Freeze the parameters for {k}")
                    v.requires_grad = False
                     
        return self.model, self.tokenizer, self.logger
    
    def model_finetuning(self):
        train_dataset = TrainDatasetForEmbedding(args=self.data_args, tokenizer=self.tokenizer)
    
        trainer = BiTrainer(
            model=self.model,
            args=self.training_args,
            train_dataset=train_dataset,
            data_collator=EmbedCollator(
                self.tokenizer,
                query_max_len=self.data_args.query_max_len,
                passage_max_len=self.data_args.passage_max_len
            ),
            tokenizer=self.tokenizer
        )
    
        Path(self.training_args.output_dir).mkdir(parents=True, exist_ok=True)
        
        trainer.train()
        trainer.save_model()
        log_df = pd.DataFrame(trainer.state.log_history)
        log_df.to_csv('./test_log.csv')
        
        if trainer.is_world_process_zero():
            self.tokenizer.save_pretrained(self.training_args.output_dir)        
    
    def model_fusing(self):
        self.model = mix_models(
            model_names_or_paths=[self.model_args.model_name_or_path, self.training_args.output_dir], 
            model_type='encoder', 
            weights=[0.5, 0.5],  # you can change the weights to get a better trade-off.
            output_path=self.training_args.output_dir + ' mixed')        

def gen_corpus(USER_SETTINGS): # optional
    json_files = []
    for root, dirs, files in os.walk(USER_SETTINGS['KB_PATH']):
        for file in fnmatch.filter(files, '*.json'):
            json_files.append(os.path.join(root, file))
    
    corpus = []
    for path_ in json_files:
        res_, _ = extract_json_know(path_, '', USER_SETTINGS['PLACE_HOLDERS'])
        corpus.append(res_)
    
    with open(USER_SETTINGS['CORPUS'], mode='w', encoding='utf-8') as f:
        for txt in corpus:
            f.write(txt+'\n')
    print('corpus developed with {} lines'.format(len(corpus)))
    
def gen_queries(all_contents_df, llm_apis, model_config, USER_SETTINGS, frac=1, content_cut=150):
    files_dir = USER_SETTINGS['KB_PATH']
    
    contents_df = all_contents_df.groupby('path').agg({'content': lambda x: ' '.join(x.astype(str))}).reset_index()
    kb_paths = contents_df['path'].tolist()
    
    q_path = os.path.join(USER_SETTINGS['TEMP_RES_PATH'], 'gen_query.jsonl')
    existing_paths = []
    with open(q_path, 'a+', encoding='utf-8') as file:
        file.seek(0)
        for i, line in enumerate(file):
            temp_q = json.loads(line.strip())['path']
            existing_paths.append(temp_q)   
    
    filtered_df = contents_df[~contents_df['path'].isin(existing_paths)]
    failed_paths = []
    
    total_len = len(filtered_df)
    count = 1
    for i, row in filtered_df.iterrows():
        print('\tid={}, there are total {} data, completion rate:{}'.format(count, total_len, np.round(count/total_len, 3)))
        pos_content = row['content']
        pos_path = row['path']
        
        # if ('地铁' in pos_path) or ('电气' in pos_path) or ('给排水' in pos_path) or ('暖通' in pos_path) or ('装修' in pos_path):
        try:
            path_processed = process_path_texts(pos_path)
            if len(pos_content) + len(path_processed) < content_cut:
                continue
            
            gen_mat = path_processed + '\n' + pos_content
            query_gen, _ = use_llm_api(llm_apis['qwen_api'],
                                        histories=[],
                                        paras={'task':'gen-ques', 
                                               'query':'', 
                                               'texts':gen_mat,
                                               'out_limit':100,
                                               'model':'qwen-long'},
                                        config=model_config)
            temp_d = {'path':pos_path, 'gen_query':query_gen, 'content':pos_content}
            count += 1
            print('Successfully generate query at {}'.format(pos_path))
        except Exception as e:
            print('WARNING: generate query at {}, \ncurrent error: {}'.format(pos_path, e))
            failed_paths.append(pos_path)
            continue
        
        with open(q_path, 'a', encoding='utf-8') as file:
            file.write(json.dumps(temp_d, ensure_ascii=False) + '\n')
        # else:
        #     print('path not in the focus list, ', pos_path)
        
    print('In total {} queries generated, there are {} paths failed, see below:\n'.format(count, len(failed_paths)))
    for fp in failed_paths:
        print(fp)

def load_gen_queries(USER_SETTINGS):
    gen_query_data = []
    q_path = os.path.join(USER_SETTINGS['TEMP_RES_PATH'], 'gen_query.jsonl')
    
    with open(q_path, 'r', encoding='utf-8') as file:
        for i, line in enumerate(file):
            gen_query_data.append(json.loads(line.strip()))
    return gen_query_data

def gen_train_data_from_contents(all_contents_df, full_path_vectors, all_vec, tokenizer, model, vectorize_texts,
                                                                                                            USER_SETTINGS,
                                                                                                            add_neg=100,
                                                                                                            frac=0.5,
                                                                                                            cutt_off=2000,
                                                                                                            topk=6):
    data_path = USER_SETTINGS['TRAIN_DATA_ALL_CONTENTS']
    files_dir = USER_SETTINGS['KB_PATH']

    checked_queries = []
    with open(data_path, 'a+', encoding='utf-8') as file:
        file.seek(0)
        for i, line in enumerate(file):
            temp_q = json.loads(line.strip())['query']
            checked_queries.append(temp_q)  
            
    know_files = []
    re_pattern = r'^[^\u4e00-\u9fff]*([\u4e00-\u9fff].*)?'
    ept_count = 0

    for root, dirs, files in os.walk(files_dir):
        for file in files:
            if ('~$' in file) or ('Meta_setting' in file):
                continue 
            else:
                know_files.append(os.path.join(root, file))
    total_len = len(know_files)   
    
    for i, pos_path in enumerate(know_files):
        query = process_path_texts(pos_path)
        
        if random.random()<=(1-frac) or query in checked_queries:
            continue
        
        if i>=total_len*frac:
            break
        
        train_data = {'query':'', 'pos': [], 'neg': []}
        train_data['query'] = query
        
        try:
            if '.json' in pos_path:
                pos_content, _ = extract_json_know(pos_path, '', USER_SETTINGS['PLACE_HOLDERS'])            
                pos_content = pos_content.strip().replace('-->', '').replace('<--', '')[cutt_off:]
            # elif '.csv' in pos_path:
            #     pos_content = pd.read_csv(pos_path, encoding='utf-8')
            #     pos_content = pos_content.to_string(index=False)
            
            pos_content = re.sub(r'[A-Za-z0-9.\t]', '', pos_content) # delete English characters and numbers
            if pos_content.strip().replace('\n', '')=='':
                print('****\tempty content found, there are {} empty json, ratio {}%***'.format(ept_count, np.round(ept_count/i,3)))
                ept_count += 1
                train_data['pos'].append(query)
            else:
                train_data['pos'].append(query + '\n' + pos_content)
            
            pred_related_res, searched_paths, voted_paths = find_relevant(query, full_paths, full_path_vectors, all_vec, all_contents_df, tokenizer, model, vectorize_texts, USER_SETTINGS, topk)
            
            neg_pool = random.sample(all_contents_df[~all_contents_df['path'].isin(list(set([pos_path] + pred_related_res)))]['path'].tolist(), add_neg)
            for neg_path in neg_pool:
                if '.json' in neg_path:
                    neg_content, _ = extract_json_know(neg_path, '', USER_SETTINGS['PLACE_HOLDERS'])
                    neg_content = neg_content.strip().replace('-->', '').replace('<--', '')[cutt_off:]
                # elif '.csv' in neg_path:
                #     neg_content = pd.read_csv(neg_path, encoding='utf-8')
                #     neg_content = neg_content.to_string(index=False)
                
                neg_head = process_path_texts(neg_path)
                neg_content = re.sub(r'[A-Za-z0-9.\t]', '', neg_content) # delete English characters
                if neg_content.strip().replace('\n', '')=='':
                    train_data['neg'].append(neg_head)
                else:
                    train_data['neg'].append(neg_head + '\n' + neg_content)
            
            print('\tid={}, completion rate:{}'.format((i+1), np.round((i+1)/(total_len*frac),3)))
            with open(data_path, 'a', encoding='utf-8') as file:
                file.write(json.dumps(train_data, ensure_ascii=False) + '\n')
        except:
            continue
    print('in total {} empty content files are found'.format(ept_count))

def gen_train_data_from_queries(gen_query_data, all_contents_df, full_path_vectors, all_vec, tokenizer, model, vectorize_texts, 
                                                                                                                            USER_SETTINGS,
                                                                                                                            add_neg=10,
                                                                                                                            topk=6):
    data_path = USER_SETTINGS['TRAIN_DATA_GEN_QUERIES']
    content_df = pd.DataFrame(gen_query_data)
    total_len = int(len(content_df))
    error = 0

    checked_queries = []
    with open(data_path, 'r', encoding='utf-8') as f:
        for line in f:
            json_obj = json.loads(line)
            if 'query' in json_obj:
                checked_queries.append(json_obj['query'])
    
    init_i = len(checked_queries)
    for i, row in content_df.iterrows():
        query = row['gen_query']
        if (query in checked_queries) or query==None:
            continue
        
        train_data = {'query':'', 'pos': [], 'neg': []}
        pos_path = row['path']
        pos_content = row['content']

        if len(pos_content)>1000:
            continue
        
        # pred_related_res, searched_paths, voted_paths = find_closest(query, full_path_vectors, all_vec, all_contents_df, tokenizer, model, vectorize_texts, USER_SETTINGS, topk)
        pred_related_res = []
        
        # neg_pool includes data far away from current embedding
        neg_pool = content_df[~content_df['path'].isin(list(set([pos_path] + pred_related_res)))]['path'].tolist()
    
        # try:
        #     pred_related_res.remove(row['path'])
        # except:
        #     print('\tfor query {}, no correct answers are found, there are {} non-founded queries'.format(query, error))
        #     error += 1
        
        train_data['query'] = query
        train_data['pos'].append((process_path_texts(pos_path, last=300).replace(r'.._知识固化库_ZJ_', '') + '\n' + pos_content))
        
        neg_num = 0
        random_neg_paths = []
        checked_neg_paths = []
        while neg_num<add_neg:
            sp = random.sample(neg_pool, 1)
            sp_content = content_df[content_df['path'].isin(sp)]['content'].values[0]
            a = len(sp_content)
            if len(sp_content)<=1000 and not sp in checked_neg_paths:
                random_neg_paths.extend(sp)
            
            checked_neg_paths.append(sp)
            neg_num += 1
        
        neg_rows = content_df[content_df['path'].isin(random_neg_paths)]
        neg_samples = []
        for _, n_row in neg_rows.iterrows():
            n_sample = process_path_texts(n_row['path'], last=300).replace(r'.._知识固化库_ZJ_', '') + '\n' + n_row['content']
            neg_samples.append(n_sample)
            
        # random_neg_samples = [process_path_texts(sp) for sp in random.sample(neg_pool, add_neg)]
        # neg_samples = random_neg_samples + [process_path_texts(pp) for pp in pred_related_res] 
        train_data['neg'].extend(neg_samples)
        
        with open(data_path, 'a', encoding='utf-8') as file:
            file.write(json.dumps(train_data, ensure_ascii=False) + '\n')
        
        err_rate = 1 - np.round(error/((i+1)-init_i), 3)
        print('\tid={}, there are total {} data, completion rate:{}, estimated acc {}'.format((i+1), total_len, np.round((i+1)/total_len, 3), err_rate))
    
    print('initial error rate: {}'.format(error/total_len))

def gen_train_data_from_interactions(USER_SETTINGS, query, sim_contents, selected_ids, all_contents_df=None, mode='use path', add_neg=0):
    
    def add_pos_neg_data(path_item, match_dfs, train_data, selected_id_set, filtered_all_contents_df=pd.DataFrame(), filter_items=[]):
        try:
            if len(filtered_all_contents_df)>0:
                filtered_all_contents_df = filtered_all_contents_df[~filtered_all_contents_df['path'].isin(filter_items)]
        except Exception as e:
            print(f'\tremoving path for generating training data failed at {path_item}, the error is {e}')
        
        try:
            content_item, raw_texts = extract_know(match_dfs)            
        except Exception as e:
            print(f'\textracting knowledge for training data failed at {path_item}, the error is {e}')
            content_item = path_item
        
        if mode=='use path':
            if id in selected_id_set:
                train_data['pos'].append(path_item)
            else:
                train_data['neg'].append(path_item)
                
        elif mode=='use content':
            if id in selected_id_set:
                train_data['pos'].append(content_item)
            else:
                train_data['neg'].append(content_item)
                
        elif mode=='both':
            if id in selected_id_set:
                train_data['pos'].extend([path_item, content_item])
            else:
                train_data['neg'].extend([path_item, content_item])
        else:
            pass
        
        return train_data, filtered_all_contents_df
    
    if mode=='use path':  
        data_path = USER_SETTINGS['TRAIN_DATA_PATH']
    elif mode=='use content':
        data_path = USER_SETTINGS['TRAIN_DATA_CONTENT']
    else:
        data_path = USER_SETTINGS['TRAIN_DATA_BOTH']
        
    train_data = {'query':query, 'pos': [], 'neg': []}
    filtered_all_contents_df = all_contents_df
    
    for id, path_item in enumerate(sim_contents):
        match_dfs = all_contents_df[all_contents_df['path'].isin([path_item])]
        train_data, filtered_all_contents_df = add_pos_neg_data(path_item, match_dfs, train_data, set(selected_ids), filtered_all_contents_df, filter_items=[path_item])

    if add_neg>0:
        add_neg = min(add_neg, len(filtered_all_contents_df))
        random_neg_df = filtered_all_contents_df.sample(n=add_neg)
        neg_grouped = random_neg_df.groupby('path')
        
        for neg_path, _ in neg_grouped:
            neg_match_dfs = all_contents_df[all_contents_df['path'].isin([neg_path])]
            train_data, _ = add_pos_neg_data(neg_path, neg_match_dfs, train_data, set(), filter_items=[])   
    
    local_train_data = []
    with open(data_path, 'a', encoding='utf-8') as file:
        file.write(json.dumps(train_data, ensure_ascii=False) + '\n')

    with open(data_path, 'r', encoding='utf-8') as file:
        for i, line in enumerate(file):
            try:
                local_train_data.append(json.loads(line.strip()))
            except Exception as e:
                print(f'{e}, at the {i} line of the training data.')
    return local_train_data

if __name__ =="__main__":
    print('loading done.')
    
    
    