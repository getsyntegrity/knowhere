"""
Prompt Service for Document Parsing
Only contains prompts required for document parsing workflow.

Removed prompts for:
- RAG/Knowledge Base: talk-kb, merge-answers, judge-kb, rerank, connect-kb, detect-contradict
- Document Generation: gen-titles-oneoff, gen-root-titles, gen-thoughts, reason-content-layout, 
                       rewrite-paras, rewrite-sentence, construct-table, reason-source
- Table Filling: filling-tb-kv, filling-tb-ck
- Other: eval-images, gen-table-query
"""

from shared.services.ai.response_process_service import process_llm_history


def build_prompt(task, texts, query, **kwargs):
    from loguru import logger
    logger.debug(f"build_prompt 调用: task={task}, texts长度={len(str(texts)) if texts else 0}")
    his_record = process_llm_history(kwargs.get('paras', {}))
    logger.debug("process_llm_history 完成")
    temperature = 0.1
    top_p = 0.1
    max_tokens = 2000
    prompt = ""

    # ==================== Text Processing Prompts ====================

    if task == 'summary':
        max_tokens = kwargs['paras']['max_tokens']
        prompt = f"""
        You will receive a text passage:
        '''
        {texts}
        '''
        Your task and requirements:
        - Extract the main content of the material, not exceeding {max_tokens} characters
        - Your response must be in the SAME LANGUAGE as the input text
        - Do not return any additional explanations beyond the extracted main content
        """
        
    elif task == 'summary-keywords':
        max_tokens = kwargs['paras']['max_tokens']
        kw_num = kwargs['paras']['kw_num']

        example = '''
         {"answer":"keyword1;keyword2;keyword3"}
        '''
        
        prompt = f"""
        You will receive a text passage:
        '''
        {texts}
        '''
        Your task is to extract keywords, no more than [{kw_num}] keywords. Note:
        - Your response must be in JSON dictionary format with key "answer" and value being the extracted keywords
        - Keywords should reflect the text theme, separated by semicolons ";"
        - Keywords must be in the SAME LANGUAGE as the input text
        - Example format:
        {example}
        - Do not output any additional explanations or descriptions besides the keywords
        """

    # ==================== Heading/Structure Prompts ====================

    elif task == 'eval-headings':
        temperature = 0
        top_p = 0.01
        max_depth = kwargs['paras']['max_depth']
        max_tokens = kwargs['paras']['max_tokens']

        prompt = f"""
        You are a document structure correction expert. You will receive an HTML table with multiple rows of text, where each row may be a heading or body text, including:
        1. id column: line number
        2. heading column: text content
        3. level column: preliminary estimated level (may be inaccurate), as follows:
            1 represents `<h1>`, 2 represents `<h2>`, and so on
            -1 indicates the text is estimated as "body text", not a heading
            Not Sure indicates the level is undetermined

        Data:
        '''
        {texts}
        '''

        ***Your task is*** to [adjust text levels to form an outline with clear and accurate parent-child relationships]. Your available actions:
        1. If you believe the current row's level estimate is accurate, keep it unchanged
        2. If you believe the current row's level estimate is inaccurate, adjust it to the correct level (integer from 1-{max_depth})
        3. If you believe the current row is more suitable as body text rather than a heading, adjust its level to -1

        ***Principles to follow*** when making the above judgments:
        1. Pay attention to parent-child level relationships between consecutive candidate texts
        2. Levels between consecutive headings cannot skip (e.g., jumping from level 1 to level 3)

        ***Output requirements***
        - Output must be a [JSON array] only, each element should contain the following fields in order:
            - "id": original line number (integer);
            - "level": the new adjusted level for that row (integer from 1~{max_depth} or -1)

        ***Other requirements***
        - Output only standard JSON, do not add any format wrappers (e.g., do not add ```json)
        - Do not add escaped newlines or other control characters
        - Do not add any explanations, comments, or descriptive text
        """

    # ==================== Image Processing Prompts ====================

    elif task == "summary-images":
        temperature = 0.1
        max_tokens = int(kwargs['paras']['max_tokens'] * 1.2)
        if texts.strip():
            img_context = f"- Image context is [{texts}], you may reference the title for summarization"
        else:
            img_context = ""

        prompt = f'''
        You will receive an image, which may be a photo, chart, or an image requiring OCR.
        Your task is to extract the main content described in the image. Note:
        - Provide a precise and concise summary, using text descriptions only, avoid extracting specific data from the image
        - Your response must be in the SAME LANGUAGE as any text visible in the image (or the context if provided)
        {img_context}
        - Do not output any additional explanations or descriptions beyond the summary
        '''

    elif task == "ocr-image":
        temperature = 0.1

        prompt = f'''
        You will receive an image, which may be a photo, chart, or an image requiring OCR.
        Your task is to perform OCR operation, fully extract and return the image content. Note:
        - Preserve the original language of the text in the image
        - Do not return any additional explanations or descriptions beyond the image content
        '''

    elif task == "ask-image":
        temperature = 0.1
        max_tokens = int(kwargs['paras']['max_tokens'] * 1.2)

        prompt = f'''
        You will receive one or more images and the user's current question: [{query}]
        You may also receive context related to the image(s).
        
        {texts}
        
        Your task is to answer the user's question based on the image(s) and context (if any). Note:
        - Your response must be in JSON format with key "answer" and value being the answer
        - Your answer must be in the SAME LANGUAGE as the user's question
        - Provide a complete and accurate answer with some explanation, but not exceeding {max_tokens} characters
        - If the image content is unrelated to the user's question, the answer should be "null"
        '''

    elif task == "judge-image-type":
        temperature = 0.1
        prompt = f'''
        You will receive an image. Your task is to determine whether the image is primarily text-based or image-based. Note:
        - Text-based images include posters, display boards, scanned documents, etc.
        - All images except those with rich text content are considered image-based
        - Output strictly in JSON dictionary format with key "answer" and value can only be "text" or "image"
        - Do not return any additional explanations or descriptions
        '''

    # ==================== Table Processing Prompts ====================

    elif task == "detect-table-headers":
        temperature = 0.1
        context = f'        {texts}'

        prompt = f'''
        You are an intelligent assistant familiar with table data structures. You will receive the first few rows of a table (in HTML format).
        
        {context}
        
        Your task is: identify the header rows of this table, considering the possibility of MultiIndex (multi-level index) headers.
        You must strictly follow these requirements:
        - You need to determine the **consecutive rows that may constitute the header**, i.e., all rows of the MultiIndex
        - The result should be a **list of row numbers where headers are located** (0-indexed), for example:
            - If only the first row is a header, the result is `[0]`
            - If rows 1-3 are all headers (multi-level index), the result is `[0, 1, 2]`
        
        - If you cannot determine, please return an empty list `[]`
        - Only return a JSON object in the following format with key "answer" and value being the result:
        ```json
        {{
          "answer": [<row_number1>, <row_number2>, ...]
        }}
        '''

    # ==================== TOC Detection Prompts ====================

    elif task == "detect-toc-range":
        temperature = 0.1
        max_tokens = 100
        start_idx = kwargs['paras']['start_idx']
        end_idx = kwargs['paras']['end_idx']

        prompt = f"""You are a document analysis expert. You need to identify the actual start and end positions of the table of contents from the candidate region.

        [Candidate Region Information]
        - Candidate region start line number: {start_idx}
        - Candidate region end line number: {end_idx}

        [Candidate Region Content]
        {texts}

        [Judgment Rules]
        Please analyze the above content and find the actual start and end line numbers of the table of contents region:

        1. **TOC Line Characteristics**:
        - Starts with "Table of Contents", "Contents", "目录", "目次", etc.
        - Usually contains chapter numbers or serial numbers (e.g., "1.", "Chapter 1", "一、", "第一章", etc.)
        - Contains heading text, usually with page numbers at the end
        - Format is relatively uniform and neat, with ellipsis "..." possible in the middle of line text
        - Most line numbers are consecutive
        - TOC region should include the line containing keywords like "Table of Contents", "Contents", "目录" if they exist

        [Output Format]
        Output in JSON format:
        {{
            "toc_start": number,  // TOC content start line number (absolute line number)
            "toc_end": number,    // TOC content end line number (absolute line number)
            "confidence": "high" | "medium" | "low"  // Confidence level
        }}

        If no TOC region matching the above characteristics exists in the input content, output:
        {{
            "toc_start": null,
            "toc_end": null,
            "confidence": "low"
        }}

        Output JSON only, do not output anything else
        """

    # ==================== Unknown Task ====================

    else:
        from loguru import logger
        logger.warning(f"Unknown task: {task}, returning empty prompt")
        prompt = ""

    return prompt, temperature, top_p, max_tokens