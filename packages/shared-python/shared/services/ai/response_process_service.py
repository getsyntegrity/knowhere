import json
import re

from loguru import logger

from shared.core.exceptions.domain_exceptions import LLMServiceException


def process_llm_history(
    paras, his_k=10
):  # under development, if we need to parse the history
    his_record = ""
    try:
        logger.debug(
            f"process_llm_history start: paras keys={list(paras.keys()) if paras else 'None'}"
        )
        histories = paras.get("histories", [])
        try:
            use_his = paras.get("use_his", False)
        except:
            use_his = False

        if len(histories) >= 1 and use_his:
            his_infos = histories[-his_k:]
            for i, his in enumerate(his_infos):
                his_record += (
                    f"Previous question {i + 1}: {his[0]}    "
                    f"Previous answer {i + 1}: {his[1]}\n"
                )
            his_record = his_record.strip()
    except:
        pass
    return his_record


def eval_response(resp, answer_key=None):
    logger.debug(f"eval_response resp: {resp}")
    if isinstance(resp, str):
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", resp)
    else:
        logger.error(f"Model response is not a string, returning directly\n{resp}")
        raise LLMServiceException(
            internal_message=f"LLM response is not a string: {type(resp).__name__}",
            provider="unknown",
        )

    try:
        # Try parsing JSON directly first.
        logger.debug(f"eval_response cleaned: {cleaned}")
        answer = json.loads(cleaned)
        logger.debug("Parsed JSON directly successfully")
        if answer_key is not None:
            answer = answer.get(answer_key, answer)
        return answer
    except Exception as e:
        logger.warning(
            f"Direct JSON parse failed; retrying with fenced JSON extraction: {e}"
        )
    # Try extracting content from a ```json ... ``` fenced block.
    match = re.search(r"```json\s*([\s\S]*?)\s*```", cleaned, re.DOTALL)
    if match:
        json_block = match.group(1).strip()
    else:
        # Fall back to stripping ```json / ``` wrappers without relying on regex matches.
        json_block = re.sub(r"^```json", "", cleaned)
        json_block = re.sub(r"```$", "", json_block).strip()
    try:
        logger.debug(f"eval_response json_block: {json_block}")
        answer = json.loads(json_block)
        logger.debug("Parsed JSON from markdown fence successfully")
        if answer_key is not None:
            answer = answer.get(answer_key, answer)
        return answer
    except json.JSONDecodeError as e:
        logger.warning(
            f"All JSON parse strategies failed; returning the raw string\n{resp}"
        )
        return cleaned
