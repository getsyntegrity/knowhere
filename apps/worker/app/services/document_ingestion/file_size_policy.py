from __future__ import annotations


SUPPORT_EMAIL = "team@knowhereto.ai"
ISSUES_URL = "https://github.com/Ontos-AI/knowhere/issues"


def build_file_size_limit_message(*, limit_mb: int, file_extension: str) -> str:
    return (
        f"File size exceeds the {limit_mb}MB limit for "
        f"{file_extension or 'this file'}. For larger files, contact "
        f"{SUPPORT_EMAIL} or open an issue at {ISSUES_URL}."
    )
