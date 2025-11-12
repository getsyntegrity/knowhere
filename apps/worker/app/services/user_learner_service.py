import os

import numpy as np
import torch as T
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.nn import TransformerEncoder, TransformerEncoderLayer

# 延迟导入避免循环导入


class CBD_Memory():
    def __init__(self, K, input_dim, model, tokenizer, N=2, lr=0.001, batch_size=2, n_epochs=3, user_dir=''):
        self.content_lengths = []
        self.intention_embeds = []
        self.contents_embeds = []
        self.opt_user_selections = []
        self.opt_pred_selections = []
        self.opt_user_markers = []
        self.opt_pred_markers = []
        self.lr = lr
        self.batch_size = batch_size
        self.n_epochs = n_epochs
        self.N = N
        self.K = K
        self.num_heads = 4
        self.num_transformer_layers = 2
        self.fc_dim = 256
        # 延迟导入避免循环导入
        from app.services.knowledge.rag_service import vectorize_texts
        self.vec_func = vectorize_texts
        self.model = model
        self.tokenizer = tokenizer
        self.user_dir = user_dir
        # below, '2' for the same dimension of contents and intentions
        self.seque_learner = SequencePredictor(self.K, 2*input_dim, self.lr, self.num_heads, self.num_transformer_layers, self.fc_dim, chkpt_dir=self.user_dir)
        self.marker_learner = MarkerPredictor(2*input_dim, self.lr, self.num_heads, self.num_transformer_layers, self.fc_dim, chkpt_dir=self.user_dir)
    def eval(self, reply_len, user_intention, sim_contents, user_selected_ids, current_markers):
        _, intention_embed = self.vec_func(user_intention, self.tokenizer, self.model)
        _, content_embeds = self.vec_func(sim_contents, self.tokenizer, self.model)        
        
        # generate ground true ids (tensors)
        true_user_ids = [0] * self.K
        for idx in user_selected_ids:
            true_user_ids[idx] = 1
        # generate ground true marker (tensors)
        marker_tensors = T.tensor(current_markers)
        
        # each time we interact with the system, it generates a data sample and records it
        self.store_memory(reply_len, intention_embed.reshape(1, -1), content_embeds, true_user_ids, marker_tensors)
        
        # if the data sample is enough, launch the learning
        current_len = len(self.intention_embeds)
        if current_len % self.N==0:
            self.learn()
        else:
            print('cumulative steps not enough: currently {} < X * {}'.format(current_len, self.N))
    
    def generate_batches(self):
        n_opts = len(self.intention_embeds)
        batch_start = np.arange(0, n_opts, self.batch_size)
        
        indices = np.arange(n_opts, dtype=np.int64)
        np.random.shuffle(indices) # generate training batches with random sampling
        batches = [indices[i:i + self.batch_size] for i in batch_start]
        
        return np.array(self.contents_embeds), np.array(self.intention_embeds), np.array(self.opt_user_selections), np.array(self.opt_user_markers), batches
    
    def learn(self):
        # load states
        try:
            self.seque_learner.load_checkpoint()
            self.marker_learner.load_checkpoint()
            
        except:
            print('loading trained parameters fails, there is no such parameters...check the file path')
        
        for _ in range(self.n_epochs):
            content_embeds, intention_embeds, true_user_ids, true_user_markers, batches = self.generate_batches()
            
            for batch in batches:
                self.seque_learner.optimizer.zero_grad()
                
                batch_content_embeds = content_embeds[batch] # should be bs, seq_len, embedding
                batch_intent_embeds = intention_embeds[batch]
                
                batch_intent_embeds = np.repeat(batch_intent_embeds, self.K, axis=1)
                batch_embeddings = np.concatenate((batch_content_embeds, batch_intent_embeds), axis=2)
                batch_embeddings = T.tensor(batch_embeddings).to(self.seque_learner.device)
                
                batch_pids = self.seque_learner(batch_embeddings)
                batch_uids = T.tensor(true_user_ids[batch]).float().to(self.seque_learner.device)
                
                batch_pmks = self.marker_learner(batch_embeddings)
                batch_umks = T.tensor(true_user_markers[batch]).float().to(self.marker_learner.device)
                
                criterion = nn.BCELoss()
                seq_loss = criterion(batch_pids, batch_uids)
                mak_loss = criterion(batch_pmks, batch_umks)
                
                print('\tsequence learner loss {}, marker loss {}'.format(seq_loss.data.detach(), mak_loss.data.detach()))
                seq_loss.backward()
                mak_loss.backward()
                
                self.seque_learner.optimizer.step()
                self.marker_learner.optimizer.step()
        # save states     
        self.seque_learner.save_checkpoint()
        self.marker_learner.save_checkpoint()
        
    def store_memory(self, length, intention_embed, content_embeds, user_ids, user_markers, pred_ids=None, pred_marker=None):
        self.content_lengths.append(length)
        self.intention_embeds.append(intention_embed)
        self.contents_embeds.append(content_embeds)
        self.opt_user_selections.append(user_ids)
        self.opt_user_markers = user_markers
        
        if not pred_ids==None:
            self.opt_pred_selections.append(pred_ids)
        if not pred_marker==None:
            self.opt_pred_markers.append(pred_marker)

    def clear_memory(self):
        self.intention_embeds = []
        self.content_lengths = []
        self.opt_user_selections = []
        self.opt_pred_selections = []
        self.opt_user_markers = []
        self.opt_pred_markers = []


class SequencePredictor(nn.Module):
    def __init__(self, K, input_dim, lr, num_heads=4, num_transformer_layers=2, fc_dim=256, chkpt_dir=''):
        super(SequencePredictor, self).__init__()
        embedding_dim = input_dim
        
        encoder_layers = TransformerEncoderLayer(embedding_dim, num_heads)
        self.transformer_encoder = TransformerEncoder(encoder_layers, num_transformer_layers)
        self.fc1 = nn.Linear(embedding_dim, fc_dim)
        self.fc2 = nn.Linear(fc_dim, K)
        
        self.checkpoint_file = os.path.join(chkpt_dir, 'seq_pred')

        self.optimizer = optim.Adam(self.parameters(), lr=lr)
        self.device = T.device('cuda:0' if T.cuda.is_available() else 'cpu')
        self.to(self.device)

    def forward(self, opt_embeddings):
        transformer_out = self.transformer_encoder(opt_embeddings)
        # Use mean of transformer outputs as sequence representation
        seq_vector = transformer_out.mean(dim=1)

        fc_res = F.relu(self.fc1(seq_vector))
        preds = T.sigmoid(self.fc2(fc_res)) # sigmoid for multi-label classification, each element is independently considered
        return preds

    def save_checkpoint(self):
        checkpoint = {
            'model_state_dict': self.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
        }
        T.save(checkpoint, self.checkpoint_file)

    def load_checkpoint(self):
        checkpoint = T.load(self.checkpoint_file, map_location=self.device)
        
        self.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.to(self.device)


class MarkerPredictor(nn.Module):           
    def __init__(self, input_dim, lr, num_heads=4, num_transformer_layers=2, fc_dim=256, out_dim=3, chkpt_dir=''):
        super(MarkerPredictor, self).__init__()
        embedding_dim = input_dim
        
        encoder_layers = TransformerEncoderLayer(embedding_dim, num_heads)
        self.transformer_encoder = TransformerEncoder(encoder_layers, num_transformer_layers)
        self.fc1 = nn.Linear(embedding_dim, fc_dim)
        self.fc2 = nn.Linear(fc_dim, out_dim) # out_dim=3, the '3' for 3 actions: rewrite, return, query

        self.checkpoint_file = os.path.join(chkpt_dir, 'mark_pred')
        
        self.optimizer = optim.Adam(self.parameters(), lr=lr)
        self.device = T.device('cuda:0' if T.cuda.is_available() else 'cpu')
        self.to(self.device)

    def forward(self, opt_embeddings):
        transformer_out = self.transformer_encoder(opt_embeddings)
        seq_vector = transformer_out.mean(dim=1)

        fc_res = F.relu(self.fc1(seq_vector))
        preds = T.sigmoid(self.fc2(fc_res))
        return preds

    def save_checkpoint(self):
        checkpoint = {
            'model_state_dict': self.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
        }
        T.save(checkpoint, self.checkpoint_file)

    def load_checkpoint(self):
        checkpoint = T.load(self.checkpoint_file, map_location=self.device)
        
        self.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.to(self.device)
        
        
        

