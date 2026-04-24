"""
Fragment Parser - for user-pasted text content injection

This parser handles .fragment files which represent user-pasted text content
that needs to be injected into the knowledge base without requiring a physical file.
"""

import os

from app.services.document_parser.md_parser import parse_md
from loguru import logger

from shared.core.config import settings
from shared.utils.file_utils import path_handle
from shared.utils.OpenAICompatibleClientSync import get_openai_client


def generate_fragment_title(content: str, max_tokens: int = 30) -> str:
    """
    Generate a concise title for fragment content using AI.

    Args:
        content: The fragment text content
        max_tokens: Maximum tokens for the generated title

    Returns:
        Generated title string
    """
    try:
        title_prompt = (
            "Generate a concise title (under 10 words) for the following text. "
            "Return ONLY the title, no quotes or explanation:\n\n"
            f"{content[:500]}"
        )
        generated_title = get_openai_client().chat_completion(
            messages=[{"role": "user", "content": title_prompt}],
            max_tokens=max_tokens,
            timeout=30,
        )
        if generated_title:
            return str(generated_title).strip()[:50]
        return None
    except Exception as e:
        logger.warning(f"Failed to generate fragment title via AI: {e}")
        return None


def parse_fragment(
    fragment_content: str,
    filename: str = None,
    output_dir: str = None,
    kb_dir: str = "Default_Root",
    base_llm_paras: dict = None,
    **kwargs,
):
    """
    Parse user-pasted fragment content.

    Args:
        fragment_content: The text content to parse
        filename: Optional filename, if not provided will be auto-generated
        output_dir: Base output directory
        kb_dir: Knowledge base directory name
        base_llm_paras: LLM parameters for parsing

    Returns:
        tuple: (full_output_dir, relative_root, parsed_df)
    """
    split_char = settings.SPLIT_CHAR or "/"

    # Generate filename if not provided or is just ".fragment"
    if not filename or filename.lower() in [".fragment", "fragment", ""]:
        generated_title = generate_fragment_title(fragment_content)
        if generated_title:
            filename = path_handle(generated_title, mode="clean_single") + ".fragment"
        else:
            filename = f"fragment_{os.urandom(4).hex()}.fragment"

    logger.debug(f"Fragment filename: {filename}")

    # Build relative_root and full_output_dir
    kb_dir_parts = kb_dir.split(split_char)
    relative_root = "/".join(kb_dir_parts + [filename])
    full_output_dir = os.path.join(output_dir, relative_root.replace("/", os.sep))
    full_output_dir = path_handle(full_output_dir, mode="sanitize")
    os.makedirs(full_output_dir, exist_ok=True)

    logger.debug(f"Fragment relative_root: {relative_root}")
    logger.debug(f"Fragment full_output_dir: {full_output_dir}")

    # Parse fragment content using md_parser
    txt_lines = fragment_content.splitlines() if fragment_content else []
    parsed_df = parse_md(
        full_output_dir,
        source_type="md",
        md_lines=txt_lines,
        base_llm_paras=base_llm_paras,
        relative_root=relative_root,
    )

    return full_output_dir, relative_root, parsed_df
