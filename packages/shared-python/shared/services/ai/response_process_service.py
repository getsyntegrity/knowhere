import json
import re

from loguru import logger


def process_llm_history(paras, his_k=10): # under development, if we need to parse the history
    his_record = ''
    try:
        logger.debug(f"process_llm_history 开始，paras keys: {list(paras.keys()) if paras else 'None'}")
        histories = paras.get('histories', [])
        try:
            use_his = paras.get('use_his', False)
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
    logger.debug(f'eval_response resp: {resp}')
    if isinstance(resp, str):
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', resp)
    else:
        logger.error(f'❌模型返不是字符串 直接返回\n{resp}')
        raise

    try:
        # 直接尝试解析 JSON
        logger.debug(f'eval_response cleaned: {cleaned}')
        answer = json.loads(cleaned)
        logger.debug(f'✅ 直接解析 JSON 成功')
        if answer_key is not None:
            answer = answer.get(answer_key, answer)
        return answer
    except Exception as e:
        logger.warning(f'⚠️ 直接解析失败，尝试提取JSON标识再解析 {e}')
    # 尝试提取 ```json ... ``` 中的内容
    match = re.search(r'```json\s*([\s\S]*?)\s*```', cleaned, re.DOTALL)
    if match:
        json_block = match.group(1).strip()
    else:
        # 尝试手动去除 ```json / ``` 包裹（不依赖匹配）
        json_block = re.sub(r'^```json', '', cleaned)
        json_block = re.sub(r'```$', '', json_block).strip()
    try:
        logger.debug(f'eval_response json_block: {json_block}')
        answer = json.loads(json_block)
        logger.debug(f'✅ 通过 markdown 包裹内容解析 JSON 成功')
        if answer_key is not None:
            answer = answer.get(answer_key, answer)
        return answer
    except json.JSONDecodeError as e:
        logger.warning(f'❌ 所有解析方式均失败，返回原始字符串\n{resp}')
        return cleaned
    
            
    
    


