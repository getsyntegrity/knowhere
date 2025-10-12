import re
import json


def process_llm_history(paras, his_k=10): # under development, if we need to parse the history
    his_record = ''
    try:
        histories = paras['histories']
        try:
            use_his = paras['use_his']
        except:
            use_his = False
            
        if len(histories)>=1 and use_his:
            his_infos = histories[-his_k :]
            for i, his in enumerate(his_infos):
                his_record += f"""历史提问{i+1}：{his[0]}    历史回答{i+1}：{his[1]}\n"""
            his_record = his_record.strip()
    except:
        pass
    return his_record

def eval_response(resp, answer_key=None):
    if isinstance(resp, str):
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', resp)
    else:
        print(f'❌模型返不是字符串 直接返回\n{resp}')
        raise

    try:
        # 直接尝试解析 JSON
        answer = json.loads(cleaned)
        print('✅ 直接解析 JSON 成功')
        if answer_key is not None:
            answer = answer.get(answer_key, answer)
        return answer
    except Exception as e:
        print(f'⚠️ 直接解析失败，尝试提取JSON标识再解析 {e}')
    # 尝试提取 ```json ... ``` 中的内容
    match = re.search(r'```json\s*([\s\S]*?)\s*```', cleaned, re.DOTALL)
    if match:
        json_block = match.group(1).strip()
    else:
        # 尝试手动去除 ```json / ``` 包裹（不依赖匹配）
        json_block = re.sub(r'^```json', '', cleaned)
        json_block = re.sub(r'```$', '', json_block).strip()
    try:
        answer = json.loads(json_block)
        print('✅ 通过 markdown 包裹内容解析 JSON 成功')
        if answer_key is not None:
            answer = answer.get(answer_key, answer)
        return answer
    except json.JSONDecodeError as e:
        print(f'❌ 所有解析方式均失败，返回原始字符串\n{resp}')
        return cleaned
    
            
    
    


