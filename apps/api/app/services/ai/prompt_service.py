import random
from app.services.ai.response_process_service import process_llm_history


def build_prompt(task, texts, query, **kwargs):
    his_record = process_llm_history(kwargs['paras'])
    temperature = 0.1
    top_p = 0.1
    max_tokens = 2000
    prompt = ""

    if task=='talk-kb':
        max_tokens = kwargs['paras']['max_tokens']
        add_req = f"- {kwargs['paras']['add_req']}"

        prompt = f"""
            你将接收用户问题：'''{query}'''
            你可能将接收到一些基础知识和资料：
            '''
                {texts}
            '''
            请参考基础知识资料，回答用户问题，注意：
            - 回答的字数不要超过{max_tokens}字。
            {add_req}
            - 除回答问题外，不要输出额外解释说明
        """

    elif task=='merge-answers':
        max_tokens = kwargs['paras']['max_tokens']

        prompt = f"""
            你是一名资深研究人员，正在进行覆盖多文档多模态的深度调研任务【{query}】
            你将接收以下表格，包含了【不同查询语句】以及【不同模态上下文】的调研结果
            '''
            {texts}
            '''
            你的任务是整理总结该表格内容，输出结论，注意：            
            - 回答的字数不要超过{max_tokens}字。
            - 如果根据调研结果无法回答问题或得出结论，只回答【可能缺少资料，我们会持续完善】
        """

    elif task=='summary':
        max_tokens = kwargs['paras']['max_tokens']
        prompt = f"""
        你将接收一段文字材料：
        '''
        {texts}
        '''
        你的任务和要求如下：
        - 提炼材料的主要内容，字数不超过{max_tokens}字
        - 除提炼的主要内容外，不要返回任何多余解释
        """
        
    elif task=='summary-keywords':
        max_tokens = kwargs['paras']['max_tokens']
        kw_num = kwargs['paras']['kw_num']

        example = '''
         {"answer":"关键词1;关键词2;关键词3"}
        '''
        
        prompt = f"""
        你将接收一段语料
        '''
        {texts}
        '''
        你的任务是提取其中关键词，数量不超过【{kw_num}】个，注意：
        - 你的回答必须是JSON字典格式，键为"answer"，值为你提取的关键词
        - 关键词要反映文本主题，关键词之间用分号";"隔开，例如
        {example}
        - 除关键词外，不要输出任何额外解释和说明
        """
        
    elif task=="judge-kb":
        max_tokens = 20
        temperature = 0.1
        prompt = f"""
            你将接收到用户的问题：'''{query}'''
            你将接收到一些基础资料：
            '''
            {texts}
            '''
            你的任务要求如下：
            - 判断基础资料中是否涉及用户问题的答案。
            - 你的返回必须是JSON字典格式，键是"judge"，值为基础知识资料或历史回答是否包含了用户问题的答案，只能 "是" 或 "否"。
            - 不要输出任何额外解释。
        """

    elif task=='reason-source':
        title = kwargs['paras']['title']
        topic = kwargs['paras']['topic']
        type = kwargs['paras']['doc_type']
        max_tokens = 20

        prompt = f"""
            你是一位{type}类文档撰写方面的专家，目前正在撰写题为 “{title}” 的{type}文件。
            你当前撰写的小节标题（或者图表名称）为：“{topic}”。

            你的任务是判断：**该部分内容是否依赖具体项目信息或企业内部资料**，以便确定是否需要检索内部知识库。
            请依据以下标准进行判断：
            - 若该内容涉及具体项目情况（地址、成本、人员、设备、合同、资质、项目特色等），则输出布尔值 "true"
            - 若内容涉及企业内部制度、组织结构、历史项目数据、业务流程、客户要求等仅在企业内部可获得的信息，则输出布尔值 "true"
            - 若该内容属于通用性知识、公有规范、行业经验总结、行业通用技术、工艺、设备等，则输出布尔值 "false"
            - 你必须**严格按照以下 JSON 格式输出**，不要添加任何其他文字说明、换行、注释：
            {{"answer": "true"}} 或者 {{"answer": "false"}}
        """

    elif task=='gen-titles-oneoff':
        topic = kwargs['paras']['topic']
        part = kwargs['paras']['part']
        avoid_parts = kwargs['paras']['avoid_parts']
        doc_type = kwargs['paras']['doc_type']
        template = kwargs['paras']['template']
        len_root = kwargs['paras']['len_root']
        max_depth = kwargs['paras']['max_depth']
        num_titles = kwargs['paras']['num_titles']
        max_tokens = kwargs['paras']['max_tokens']

        if not part.strip()=="" and not avoid_parts.strip()=="":
            demand_desc = f"                - 生成提纲可参考以下模板中的 “{part}” 部分，但禁止生成与 “{avoid_parts}” 相关的标题"
        elif part.strip()=="" and not avoid_parts.strip()=="":
            demand_desc = f"                - 生成提纲可参考以下模板，但禁止生成与 “{avoid_parts}” 相关的标题"
        elif avoid_parts.strip()=="" and not part.strip()=="":
            demand_desc = f"                - 生成提纲可参考以下模板中的 “{part}” 部分"
        else:
            demand_desc = r"生成提纲可参考以下模板"

        prompt = f"""你是【{doc_type}】文件撰写方面的专家。现在要求你以【{topic}】为主题，生成完整详细的文件提纲，具体要求如下
                - 已确定一级标题【{len_root}】个，你需要生成其他层级的标题
                - 确保提纲总层级不超过【{max_depth}】层，全部标题数量不超过【{num_titles}】个
                - 一级标题名称、撰写思路、其他层级需生成的标题数量如下
                '''
                {texts}
                '''
                {demand_desc}
                ‘’‘
                {template}
                ’‘’
                - 生成的提纲要具备清晰的父-子树形层级结构，严禁生成多余一级标题，即保持一级标题为【{len_root}】个
                - 生成的提纲层级必须遵循 Markdown 格式，即所有标题都使用"-"前缀，并使用"-"和空格区分标题层级
                - 不要生成意思重复的标题，不要返回任何其他解释说明
            """

    elif task=='gen-root-titles':
        doc_type = kwargs['paras']['doc_type']
        title = kwargs['paras']['title']
        part = kwargs['paras']['part']
        avoid_parts = kwargs['paras']['avoid_parts']
        content = kwargs['paras']['content']
        style = kwargs['paras']['style']
        num_titles = kwargs['paras']['num_titles']
        if num_titles>0:
            num_titles_req = f"注意你生成的标题只能={num_titles}"
        else:
            num_titles_req = ""
        try:
            add_req = kwargs['paras']['add_req']
        except:
            add_req = ""
                                
        prompt = f"""你的任务是生成 {doc_type} 文件的提纲，文件标题是 "{title}"。具体要求如下：
                - 仅参考和生成 "{part}" 相关提纲，禁止生成 "{avoid_parts}" 相关的提纲：
                - 仅生成一级提纲（即最高层级的章节标题），生成的一级标题有且只有【{num_titles}】个。
                - 生成的提纲遵循Markdown格式，即所有标题都使用"-"前缀分隔。
                - 提纲风格符合 {style}，除生成提纲之外不要返回任何其他解释。{add_req}
                - 生成一级提纲可参考以下样例（注意**仅参考其中的【一级标题】**） {num_titles_req}：
                - 生成一级提纲不要包括“目录”字样
                ‘’‘
                    {texts}
                ’‘’
                - 生成提纲可以参考以下内容中的 "{part}" 部分 {num_titles_req}：
                '''
                    {content}
                '''
            """

    elif task=='gen-thoughts':
        doc_type = kwargs['paras']['doc_type']
        title = kwargs['paras']['title']
        num_titles = kwargs['paras']['num_titles']
        max_tokens = int(num_titles * 200 * 1.5)

        prompt = f"""
        你是一位擅长撰写 {doc_type} 文件的专家，当前正在撰写一份标题为 "{title}" 的文档，需要你进行内容规划，要求如下：
        1. 已确定如下 {num_titles} 个一级标题（每一行一个标题，保持原样）：
        '''
        {texts}
        '''

        2. 请你严格按照输入的全部一级标题，逐一生成写作规划，**不得遗漏任何标题，不得修改标题文字，不得增删标题**
        3. 每个一级标题需输出一个对应的写作思路与拟包含的大致内容，长度不少于100字且不超过200字，语言专业
        4. 输出格式必须严格为**单层 JSON 字典**，键为原始一级标题，值为写作思路与内容规划（仅文本，不包含额外符号或解释）
        5. 最终输出应包含 **{num_titles} 个键值对，与输入标题数量完全一致**，不允许遗漏或多余
        """

    elif task=='reason-content-layout':
        title = kwargs['paras']['title']
        topic = kwargs['paras']['topic']
        type = kwargs['paras']['doc_type']
        words = int(kwargs['paras']['words'])
        num_subs = kwargs['paras']['num_subs']
        max_tokens = int(words*1.2)

        prompt = f"""你是{type}方面的撰写专家。正在撰写题目为 “{title}” 的文档中的一个小节，其主题是 “{topic}”。
                    先不生成正文，现请你规划该小节下的子主题内容，具体要求如下：
                    - 子主题之间要符合逻辑先后顺序，子主题总数不要超过 {num_subs} 个
                    - 考虑各子主题是否应包含表格或插图，注意:
                        - 仅在需展示技术概念、设备、材料、工序、图纸、技术路线、城市或地区风貌等内容时，推荐插入图片
                        - 仅在需展示具体参数、人员职责、设备列表、任务职责划分等内容时，推荐插入表格
                        - 不要插入重复意义的图片或表格
                    - 根据总字数限制 {words}，合理分配每个子主题下的字数
                    
                    输出为一个 JSON 数组，每个元素为一个子节，包含以下字段：
                    - section_id：段落编号
                    - subtopic：小节主题
                    - words：建议字数
                    - table：如有建议插入的表格，请写出表格标题；如果没有推荐或已推荐过相近意义的表格，写 null
                    - image：如有建议插入的图片，请写出图片说明标题；如果没有推荐或已推荐过相近意义的插图，写 null
                你的输出必须严格符合 JSON 格式，不要生成其他无关或解释性内容。
            """
        
    elif task=='rewrite-paras':
        title = kwargs['paras']['title']
        subtopic = kwargs['paras']['subtopic']
        type = kwargs['paras']['type']
        words = int(kwargs['paras']['words'])
        kb_texts = kwargs['paras']['kb_content']
        web_texts = kwargs['paras']['web_content']
        try:
            image = kwargs['paras']['image']
        except:
            image = None
        try:
            table = kwargs['paras']['table']
        except:
            table = None
        temperature = 0.2
        max_tokens = int(2*words)
        word_sytle = '宋体'
        word_size = 12

        if not image==None:
            img_prompt = f"""
            - 正文部分应包括图片，图片标题为"{image}"，请在正文中适当位置插入占位符，格式为：
                <!-- IMAGE: {image} -->
            """
        else:
            img_prompt = ""
        if not table==None:
            tb_prompt = f"""
            - 正文部分应包括表格，表格标题为"{table}"，请在正文中适当位置插入占位符，格式为：
                <!-- TABLE: {table} -->
                表格内容无需生成，仅保留占位符。
            """
        else:
            tb_prompt = ""

        prompt = f"""
    你是 "{type}" 方面的撰写专家。现在要求你撰写题目为 "{title}" 的文档中的一个小节的正文，采用标准 HTML 格式，并严格遵序以下要求：

    【当前小节标题】
    <h4>{subtopic}</h4>

    【格式与内容要求】
    - 正文每段使用段落格式 <p style="text-indent:2em; font-family:{word_sytle}; font-size:{str(word_size)}pt;"> 。
    - 正文总字数≥{words}，内容必须紧扣该标题，表达逻辑清晰、正式专业，不得偏离标题，不得添加无关的解释或扩展。
    - 可使用 1)、2)、3) 或 a)、b)、c) 等分点论述方式组织内容，但必须保持分点格式的一致性和连续性。
    {tb_prompt}
    {img_prompt}
    - 严禁使用 Markdown、非标准 HTML 或任意其他标记语言。

    【可参考信息】：
    1. 项目关键背景信息
    '''
    {texts}
    '''
    2. 知识库中可能相关的信息
    '''
    {kb_texts}
    '''
    3. 网络检索的可能相关信息
    '''
    {web_texts}
    '''
    """

    elif task=='rewrite-sentence':
        max_tokens = int(1.3*len(texts))
        add_req = kwargs['paras']['add_req']
        prompt =  f"""
            你的任务是重写以下句子，使其符合用户要求 "{add_req}"：
            '''{texts}'''
            你仅返回重写后的句子，不要增加引号或其他标点，不要返回额外内容。
        """

    elif task=='construct-table':
        title = kwargs['paras']['title']
        table_title = kwargs['paras']['table_title']
        topic = kwargs['paras']['topic']
        type = kwargs['paras']['type']
        kb_texts = kwargs['paras']['kb_content']
        web_texts = kwargs['paras']['web_content']

        diverse = kwargs['paras']['diverse']
        table_structures = [
            "- 本次使用**普通单层表头结构**，即表头仅一行、每列对应一个字段，无跨行或跨列情况。",
            "- 本次使用**多层级表头结构**，即使用 `<th colspan>` 或 `<th rowspan>` 分组字段。使用 `colspan` 表示横向合并字段，`rowspan` 表示纵向合并字段，须确保每行的单元格数量逻辑一致。",
            "- 本次构建**行列索引混合型表格**，即首行为列索引、首列为行索引，左上角单元格使用斜线“/”标注交叉含义（如“参数/型号”）。"
        ]
        if diverse:
            add_prompt = "【结构风格多样化】\n" + table_structures[random.randint(0, 2)]
        else:
            add_prompt = "【结构风格多样化】\n" + table_structures[0]

        prompt =  f"""
    你是 “{type}” 领域的专业撰写专家，正在为题目为 "{title}" 的文档撰写一个小节，小节主题为 “{topic}”。请根据以下要求生成一张**标准 HTML 表格**，用于插入正文中：

    【表格结构与样式要求】
    1. 表格标题为：“{table_title}”，放置于表格上方，使用以下格式包裹：
    <p style="text-align:center; font-weight:bold;">{table_title}</p>

    2. 表格使用 `<table>` 标签构建，并满足以下规范：
    - 外层结构：`<table style="border-collapse:collapse; width:100%;">`
    - 所有 `<th>` 与 `<td>` 元素统一添加：
        `style="border:1px solid black; padding:4px;"`
    - 每个单元格必须具备边框（不可使用无边样式或 colspan/rowspan 合并）
    - 表头结构清晰、层级合理，表头结构使用 `<thead>`，内容结构使用 `<tbody>`

    【内容撰写要求】
    1. 表格内容要求清晰专业，要结合以下上下文合理推理生成，禁止凭空编造与 {topic} 无关的信息；
    2. 严禁生成嵌套 `<table>`，严禁附加解释文字或额外段落；
    3. 最终输出必须仅包含：
    - `<p>` 格式表格标题段
    - 合规的 HTML `<table>` 表格结构本体

    {add_prompt}

    【表格内容可参考信息】：
    1. 项目关键背景信息
    '''
    {texts}
    '''
    2. 知识库中可能相关的信息
    '''
    {kb_texts}
    '''
    3. 网络检索的可能相关信息
    '''
    {web_texts}
    '''
    """

    elif task=='filling-tb-kv':
        temperature = 0
        top_p = 0.01

        prompt = f"""
            你是一名信息抽取和表格填写助手，请根据以下基础资料回答特定查询问题。
            基础资料如下：
            '''{texts}'''

            请根据上述资料回答以下查询关键词：
            '''{query}'''

            请严格遵守以下要求：
            1. 如果在资料中可以找到明确答案，请提取并填写该答案。
            2. 如果资料中没有包含相关信息或答案不确定，请将答案填写为 "null"。
            3. 你必须返回一个合法的 JSON 字典，结构如下：
            {{
                "answer": "（你的答案或null）"
            }}
            4. 不要输出任何解释或附加内容，仅返回 JSON 格式的答案。
        """

    elif task=='filling-tb-ck':
        temperature = 0
        top_p = 0.01
        click_context = query.split('-->')[-1]

        prompt = f"""
        你是一名专业的信息标注人员，负责根据给定资料对选项进行判断与勾选。

        请阅读以下基础资料：
        '''{texts}'''

        然后判断以下待选项中，哪些应该被勾选：
        '''{click_context}'''

        请严格按照以下规则操作：
        1. 所有待选项以字母 "R" 开头。
        2. 对于你认为应该勾选的选项，将前缀 "R" 替换为符号 "☑"；
        3. 对于你认为不应该勾选的选项，将前缀 "R" 替换为符号 "□"；
        4. 返回结果必须是一个 JSON 格式的字典，结构如下：
        {{
            "answer": "（完成勾选处理后的字符串，保留换行与原始顺序）"
        }}
        5. 不要输出任何解释或额外信息，仅返回 JSON 格式的结果。
        """

    elif task =='rerank':
        temperature = 0
        top_p = 0.01
        keep_one_req = ""
        if kwargs['paras']['keep_one']:
            keep_one_req = "- 输出结果中，至少要保留1个路径的位置编号，禁止全部排除；"

        example = '''
            假设接收的表格如下
            <table border="1" class="dataframe">
              <thead>
                <tr>
                  <th>序号</th>
                  <th>知识路径</th>
                  <th>知识点摘要</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>1</td>
                  <td>路径1</td>
                  <td>知识摘要1</td>
                </tr>
                <tr>
                  <td>2</td>
                  <td>路径2</td>
                  <td>知识摘要2</td>
                </tr>
                <tr>
                  <td>3</td>
                  <td>路径3</td>
                  <td>知识摘要3</td>
                </tr>
                <tr>
                  <td>4</td>
                  <td>路径4</td>
                  <td>知识摘要4</td>
                </tr>
              </tbody>
            </table>
            
            假设知识路径与用户提问相关度是：路径2 > 路径1 > 路径3，与提问关系不大的是路径4。
            你的返回如下（注意：序号对应原表格序号列，即表格中第1行序号为1，第2行为2，依此类推；不相关的路径直接排除，不保留其序号）：
            answer:{
                [2, 1, 3]
            }
            '''

        prompt = f"""
            你将接收到一个用户提问：'''{query}'''
            你还会接收到一个html表格，表格中每一行代表一个可能与该提问相关的知识路径与知识摘要：
            '''{texts}'''
            
            你的任务：
            - 评估每个知识文件路径与【{query}】的相关程度；
            - 按相关程度从高到低对这些路径进行重新排序；
            - 如果某个路径与提问明显无关，则直接排除，不要在最终序号列表中保留它 {keep_one_req}；
            - 排序结果必须用**原始表格中的序号**表示（原表格中第1个知识路径序号为1，第2个为2，依此类推）；
            - 可以调整顺序，但序号必须保留原始位置编号；
            {keep_one_req}
            - 输出必须是**JSON格式**的字典，键为 "answer"，值为排序后的序号列表；
            - 不要输出任何解释、额外内容或其他字段。
            
            返回格式示例：
            {example}
            """
                
    elif task=='eval-headings':
        temperature = 0
        top_p = 0.01
        max_tokens = int(kwargs['paras']['max_tokens']*1.3)
        basic_preds = kwargs['paras']['basic_preds']

        prompt = f"""
        你是一位文档结构校正专家，你将接收从原始文本中提取的候选标题 以及 初步判断的标题层级（可能不合适）。
        '''
        {texts}
        '''
        你要完成以下任务：
        1. 判断每个候选标题是否的确适合作为标题；如是，标注其正确的层级（1 表示 `<h1>`，2 表示 `<h2>`，依此类推，最大为4）；
        2. 如果某一行不应视为标题，将其修正层级标为 -1；
        3. 调整标题层级和顺序时，要遵守以下原则：
            - 严格遵循父子关系原则，层级不能跳跃（如从 h1 跳到 h3）
            - 如果2行候选标题字符重复度很高，则合并2个标题
            - 如果1个标题是孤立标题，例如1个父标题下只有1个子标题，则将该子标题修正为-1
            - 如果1个标题与同级其他标题相比，样式差别明显，又无逻辑关系，则将其修正为-1
            - 层级超过 4 的标题统一标为 -1，保持结构简洁
            - 标注和修正的标准一致，尽量不要全部标题标注为-1。
        
        4. 输出结果为 JSON 数组，数组每个元素应按顺序包含以下字段：
        - "id": 原始序号（整数）；
        - "heading": 原始标题（字符串）；
        - "level": 修正后的层级（1~4 的整数或 -1）
        
        5. 其他要求：
        - 只输出标准 JSON，不要输出其他任何格式包装（如不要加 ```json）；
        - 不要转义换行符或其他控制字符（不要输出 \u000a 等符号）；
        - 不要添加任何说明、注释或解释性文字；原始标题文本不可改动
        
        6. 参考样例：
        - 你的判断需要参考以下层级分析结果（如有），并与该结果层级逻辑一致
        {basic_preds}
        """

    elif task=="eval-images":
        temperature = 0.1
        max_tokens = int(kwargs['paras']['max_tokens']*1.5)
        prompt = f'''
        你的任务是评估图像与用户输入 "{query}" 的相关性：
        - 请从以下维度对图像进行打分（每个维度评分范围为0到1，越接近1表示该维度越符合要求）：

        1. **相关性**：图像内容在多大程度上符合用户输入 {query}。
        2. **专业性**：图像是否符合专业文档的标准，抽象概念图、卡通图等均不符合要求。
        3. **尺寸规范**：图像长宽比符合4:3或16:9，比例过于瘦或过于宽的图均需要扣分。
        4. **简洁性**：图像是否简洁明了，避免过度复杂和包含不必要的元素。

        - 请严格按照JSON字典格式输出，键为每个维度的名称，值为对应的得分。
        - 禁止输出多余解释和描述性内容。
        '''

    elif task=="summary-images":
        temperature = 0.1
        max_tokens = int(kwargs['paras']['max_tokens']*1.2)
        if texts.strip():
            img_context = f"- 图像上下文是【{texts}】 可参考标题总结"
        else:
            img_context = ""

        prompt = f'''
        你将接收一张图片，图片可能是照片、图表、需要OCR的图像等
        你的任务是提炼图片中描述的主要内容，注意：
        - 提炼精准概括，尽量仅使用文字描述，避免提取图中具体数据
        {img_context}
        - 除总结外，禁止输出多余解释和描述
        '''

    elif task=="ocr-image":
        temperature = 0.1

        prompt = f'''
        你将接收一张图片，图片可能是照片、图表、需要OCR的图像等
        你的任务是执行OCR操作，全面提取并返回图像内容，注意：
        - 除图像内的内容，禁止返回多余解释和描述
        '''

    elif task=="ask-image":
        temperature = 0.1
        max_tokens = int(kwargs['paras']['max_tokens'] * 1.2)

        prompt = f'''
        你将接收一张或多张图像以及用户当前问题【{query}】
        你还可能接受到与该图像相关的上下文
        
        {texts}
        
        你的任务是根据图像和上下文（如有）回答用户问题，注意：
        - 你的回答必须是JSON格式，键为"answer"，值为答案
        - 回答完善准确，需要包括一定的解释说明，但不超过{max_tokens}字
        - 如果图像内容与用户问题无关，答案统一为 "null"
        '''

    elif task=="judge-image-type":
        temperature = 0.1
        prompt = f'''
        你将接收一张图片，你的任务是判断该图片是以文本内容为主还是以图像内容为主，注意：
        - 以文本内容为主的图片包括海报、展板、扫描文件等
        - 除有丰富文本内容的图片外，均属于以图像为主的图片
        - 严格按照JSON字典格式输出，键为"answer"，值只能为 "text" 或 "image"
        - 禁止返回多余说明或解释
        '''

    elif task=="gen-table-query":
        temperature = 0.1
        context = f'        {texts}'

        prompt = f'''
        你是一个熟悉 pandas 和 SQL 查询的智能助手。你会收到用户查询：{query}
        你将接收到由一张表格
        
        {context}
        
        你的任务是：基于上述表格，将用户查询转化为 pandas SQL 查询语句，格式如下：
        SELECT * FROM df WHERE <条件1> AND/OR <条件2> ...
        
        请严格按以下要求输出：
        - 仅输出一行 pandas SQL 查询语句，不要额外解释，不要臆造字段
        - 对于SELECT 充分考虑查询语句【{query}】涉及的列名，不要少于5个
        - 使用表头中的真实列名，保持中文列名不变
        - 所有列名必须用反引号包裹（如 `项目名称`），以防止特殊符号引发错误
        - 数值类型直接比较（如 工程量 > 1000）
        - 如果判断该表格无法回答用户问题，或者当前条件无法从列名推断，回答为"null"
        - 必须返回JSON格式，键为"answer"，值为你的回答
        '''

    elif task=="detect-table-headers":
        temperature = 0.1
        context = f'        {texts}'

        prompt = f'''
        你是一个熟悉表格数据结构的智能助手，你将接收到一张表格的前几行（html格式）
        
        {context}
        
        你的任务是：识别该表格的表头行，需考虑表头存在 MultiIndex（多级索引）的情况
        要严格遵守以下要求：
        - 你需要判断该表格的 **表头可能占据的连续多行**，即 MultiIndex 的所有行
        - 判断结果应为 **表头所在的行号列表**（从 0 开始编号），例如
            - 如果第1行就是表头，则判断结果是 `[0]`
            - 如果第1-3行都是表头（多级索引），则判断结果是 `[0, 1, 2]`
        
        - 如果无法判断，请返回空列表 `[]`
        - 仅返回一个符合以下格式的 JSON 对象，键为"answer"，值为判断结果
        ```json
        {{
          "answer": [<行号1>, <行号2>, ...]
        }}
        '''

    elif task=="connect-kb":
        temperature = 0.1
        max_tokens = 20
        source_txt = kwargs['paras']['source_txt']
        target_txt = kwargs['paras']['target_txt']

        prompt = f'''
        你是一个严格的相似性评估器。  
        请比较以下两个知识片段的内容，判断它们在语义上的相似程度。  
        
        评分要求：  
        - 范围：0 到 1 的实数  
        - 1 表示语义完全一致  
        - 0 表示毫无相似性  
        - 允许小数（如 0.73）  
        
        片段A（源片段）：  
        {source_txt}  
        
        片段B（目标片段）：  
        {target_txt}  
        
        仅返回一个合法的 JSON 字典，格式如下：  
        {{"answer": 分数}}  
        
        不要输出任何解释说明或额外文本。
        '''

    return prompt, temperature, top_p, max_tokens


'''暂时废弃提示词代码'''
# elif task=='extract-contents':
#     doc_type = kwargs['paras']['doc_type']
#     topic = kwargs['paras']['topic']
#     avoid_topics = kwargs['paras']['avoid_topics']
    
#     prompt = f"""你是{doc_type}文件撰写方面的专家，需要分析以下内容，仅提取与{topic}有关的内容，具体要求如下：
#             '''
#             {texts}
#             '''
#             - 仅提取与{topic}相关的内容，不要提取{avoid_topics}方面的内容。
#             - 不要输出额外解释。
#         """
    
# elif task=='extract-topics':
#     doc_type = kwargs['paras']['doc_type']
#     num_topics = kwargs['paras']['num_topics']

#     prompt = f"""你是{doc_type}文件撰写方面的专家，需要分析以下内容，从总提取数个主题，具体要求如下：
#             '''
#             {texts}
#             '''
#             - 你自主判断提取的主题数量，但不能超过{num_topics}个。
#             - 保证主题涉及的内容尽量区分，不要重叠。
#             - 不要输出额外解释。
#             - 输出采用Markdown格式，使用"-"和空格区分主题。
#         """