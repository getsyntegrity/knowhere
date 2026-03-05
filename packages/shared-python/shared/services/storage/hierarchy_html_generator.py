"""
Hierarchy HTML Generator

生成层级结构可视化 HTML 文件
简洁版：白色背景，内容直接展示在叶节点下方，类似原始数据展示
"""

import json
from typing import Any, Dict


def generate_hierarchy_html(
    hierarchy_data: Dict[str, Any],
    chunks_data: Dict[str, Any],
    doc_title: str = "文档层级结构"
) -> str:
    """
    生成层级结构可视化的 HTML 内容

    Args:
        hierarchy_data: 层级结构字典（来自 hierarchy.json）
        chunks_data: chunks 数据字典（包含 {"chunks": [...]}）
        doc_title: 文档标题

    Returns:
        HTML 内容字符串
    """
    # 自动获取文档标题（如果未指定）
    if doc_title == "文档层级结构" and hierarchy_data.get("Default_Root"):
        keys = list(hierarchy_data["Default_Root"].keys())
        if keys:
            doc_title = keys[0]

    # 转义 JSON 以安全嵌入 HTML
    hierarchy_json = json.dumps(hierarchy_data, ensure_ascii=False, indent=2)
    chunks_json = json.dumps(chunks_data, ensure_ascii=False, indent=2)

    html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{doc_title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: monospace;
            background: #fff;
            color: #000;
            padding: 20px;
            font-size: 13px;
            line-height: 1.4;
        }}
        
        .tree {{
            margin-left: 0;
        }}
        
        .node {{
            margin-left: 20px;
        }}
        
        .node-header {{
            cursor: pointer;
            padding: 2px 0;
            display: flex;
            align-items: flex-start;
            gap: 4px;
        }}
        
        .node-header:hover {{
            background: #f5f5f5;
        }}
        
        .toggle {{
            color: #666;
            width: 12px;
            font-size: 10px;
            flex-shrink: 0;
            margin-top: 2px;
        }}
        
        .toggle.collapsed {{
            transform: rotate(-90deg);
        }}
        
        .label {{
            word-break: break-all;
        }}
        
        .label.branch {{
            font-weight: bold;
        }}
        
        .children {{
            overflow: hidden;
        }}
        
        .children.collapsed {{
            display: none;
        }}
        
        .content {{
            margin-left: 16px;
            padding: 8px 12px;
            background: #f9f9f9;
            border-left: 2px solid #ddd;
            margin-top: 4px;
            margin-bottom: 8px;
            white-space: pre-wrap;
            word-break: break-word;
            color: #333;
        }}
        
        .toolbar {{
            position: fixed;
            top: 10px;
            right: 10px;
            display: flex;
            gap: 8px;
        }}
        
        .btn {{
            padding: 4px 8px;
            font-size: 12px;
            cursor: pointer;
            background: #f0f0f0;
            border: 1px solid #ccc;
            font-family: monospace;
        }}
        
        .btn:hover {{
            background: #e0e0e0;
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        <button class="btn" onclick="expandAll()">展开内容</button>
        <button class="btn" onclick="collapseAll()">折叠内容</button>
    </div>
    <div class="tree" id="tree"></div>

    <script>
        const hierarchyData = {hierarchy_json};
        const chunksData = {chunks_json};
        
        // 构建路径到内容的映射
        const pathContentMap = {{}};
        if (chunksData && chunksData.chunks) {{
            chunksData.chunks.forEach(chunk => {{
                if (chunk.path) {{
                    pathContentMap[chunk.path] = chunk.content || '';
                }}
            }});
        }}
        
        // 转义HTML
        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}
        
        // 渲染树
        function renderTree() {{
            const docTree = hierarchyData['Default_Root'] || {{}};
            document.getElementById('tree').innerHTML = renderNode(docTree, '');
            bindEvents();
        }}
        
        // 递归渲染节点
        function renderNode(node, parentPath) {{
            let html = '';
            
            for (const [key, value] of Object.entries(node)) {{
                const currentPath = parentPath ? `${{parentPath}}/${{key}}` : key;
                const fullPath = 'Default_Root/' + currentPath;
                const hasChildren = value && Object.keys(value).length > 0;
                const content = pathContentMap[fullPath] || '';
                
                html += '<div class="node">';
                
                if (hasChildren) {{
                    html += `<div class="node-header" data-has-children="true">`;
                    html += `<span class="toggle">▼</span>`;
                    html += `<span class="label branch">${{escapeHtml(key)}}</span>`;
                    html += `</div>`;
                    html += `<div class="children" data-is-content="false">`;
                    html += renderNode(value, currentPath);
                    html += `</div>`;
                }} else {{
                    html += `<div class="node-header" data-has-children="false">`;
                    html += `<span class="toggle">▼</span>`;
                    html += `<span class="label">${{escapeHtml(key)}}</span>`;
                    html += `</div>`;
                    if (content) {{
                        html += `<div class="children" data-is-content="true"><div class="content">${{escapeHtml(content)}}</div></div>`;
                    }}
                }}
                
                html += '</div>';
            }}
            
            return html;
        }}
        
        // 绑定事件
        function bindEvents() {{
            document.querySelectorAll('.node-header').forEach(header => {{
                header.addEventListener('click', function() {{
                    const toggle = this.querySelector('.toggle');
                    const children = this.nextElementSibling;
                    
                    if (children && children.classList.contains('children')) {{
                        if (children.classList.contains('collapsed')) {{
                            children.classList.remove('collapsed');
                            toggle.classList.remove('collapsed');
                        }} else {{
                            children.classList.add('collapsed');
                            toggle.classList.add('collapsed');
                        }}
                    }}
                }});
            }});
        }}
        
        // 展开内容：展开所有
        function expandAll() {{
            document.querySelectorAll('.children').forEach(el => el.classList.remove('collapsed'));
            document.querySelectorAll('.toggle').forEach(el => el.classList.remove('collapsed'));
        }}
        
        // 折叠内容：只折叠叶节点内容，保持树结构展开
        function collapseAll() {{
            document.querySelectorAll('.children').forEach(el => {{
                if (el.dataset.isContent === 'true') {{
                    el.classList.add('collapsed');
                    const toggle = el.previousElementSibling?.querySelector('.toggle');
                    if (toggle) toggle.classList.add('collapsed');
                }} else {{
                    el.classList.remove('collapsed');
                    const toggle = el.previousElementSibling?.querySelector('.toggle');
                    if (toggle) toggle.classList.remove('collapsed');
                }}
            }});
        }}
        
        renderTree();
    </script>
</body>
</html>
'''
    return html_content
