"""文本处理工具函数"""

import re
import unicodedata


def slugify(text: str, max_len: int = 80) -> str:
    """将文本转为 URL 友好的 slug"""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[-\s]+", "-", text)
    return text[:max_len].rstrip("-")


def truncate(text: str, max_len: int = 200, suffix: str = "...") -> str:
    """截断文本并添加后缀"""
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)].rstrip() + suffix


def sanitize_filename(name: str) -> str:
    """移除非文件名字符"""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^\w.-]", "_", name)
