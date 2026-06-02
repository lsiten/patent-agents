"""
Per-Agent Secret Cipher — Fernet-based 加密/解密工具

用途：加密 per-agent 的 API key（存储在 agent_overrides.json），保证 rest-at-rest 安全。

设计要点：
- 主密钥来源（按优先级）：
  1. 环境变量 `AGENT_OVERRIDE_MASTER_KEY`（base64-encoded 32 字节）—— 适合 CI / 生产
  2. 文件 `<DATA_DIR>/.secret_key`（自动生成并持久化）—— 适合本地开发
- 密文格式：所有加密结果以 `enc:` 前缀 + base64(ciphertext) 形式存储
  - 解密时自动识别前缀：非 `enc:` 视为明文，原样返回（向后兼容旧 override 数据）
- 主密钥一旦丢失，加密的 API key 全部不可恢复 — 这是有意的（与设计目标一致）
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


# ── 模块状态 ─────────────────────────────────────────────────────────
# _DATA_DIR 在 conftest.py 里用 monkeypatch 替换，测试时可以指向 tmp_path
# 默认指向 backend/data/
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
_DATA_DIR: Path = _BACKEND_DIR / "data"
_SECRET_KEY_FILE: str = ".secret_key"
_ENV_MASTER_KEY: str = "AGENT_OVERRIDE_MASTER_KEY"

# 加密输出前缀
_ENC_PREFIX: str = "enc:"

# 全局缓存的 master key（避免每次加密都读文件 / env）
_cached_key: Optional[bytes] = None


def _get_master_key() -> bytes:
    """
    获取主密钥，优先级：
    1. 环境变量 AGENT_OVERRIDE_MASTER_KEY
    2. <DATA_DIR>/.secret_key 文件
    3. 自动生成新 key 并写入文件
    """
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    # 1. env
    env_key = os.environ.get(_ENV_MASTER_KEY)
    if env_key:
        try:
            _cached_key = env_key.encode("utf-8")
            # 验证 key 合法（Fernet 要求 base64-encoded 32 字节）
            Fernet(_cached_key)
            return _cached_key
        except (ValueError, Exception) as e:
            logger.warning(
                "Invalid %s in env, falling back to file: %s",
                _ENV_MASTER_KEY,
                e,
            )
            _cached_key = None

    # 2. 文件
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    key_file = _DATA_DIR / _SECRET_KEY_FILE
    if key_file.exists():
        try:
            stored = key_file.read_text(encoding="utf-8").strip()
            if stored:
                _cached_key = stored.encode("utf-8")
                Fernet(_cached_key)  # 验证
                return _cached_key
        except (ValueError, Exception) as e:
            logger.warning("Invalid secret key file, regenerating: %s", e)
            _cached_key = None

    # 3. 自动生成
    new_key = Fernet.generate_key()
    key_file.write_bytes(new_key)
    try:
        os.chmod(key_file, 0o600)  # 仅 owner 可读写
    except OSError:
        pass  # Windows 不支持 chmod
    _cached_key = new_key
    logger.info(
        "Generated new secret key at %s — keep it safe, "
        "losing it will invalidate all encrypted API keys",
        key_file,
    )
    return _cached_key


def _get_fernet() -> Fernet:
    return Fernet(_get_master_key())


def encrypt_value(plaintext: str) -> str:
    """
    加密明文。返回 `enc:<Fernet-ciphertext>` 格式。
    Fernet 内部已是 base64 编码，直接拼接前缀即可。
    空字符串直接返回空（不浪费密文）。
    """
    if not plaintext:
        return ""
    f = _get_fernet()
    cipher = f.encrypt(plaintext.encode("utf-8"))
    return _ENC_PREFIX + cipher.decode("ascii")


def decrypt_value(ciphertext: str) -> str:
    """
    解密。如果 ciphertext 以 `enc:` 开头则解密；否则视为明文原样返回。
    解密失败抛 InvalidToken。
    """
    if not ciphertext:
        return ""
    if not ciphertext.startswith(_ENC_PREFIX):
        # 兼容未加密的旧数据
        return ciphertext
    f = _get_fernet()
    raw = ciphertext[len(_ENC_PREFIX):].encode("ascii")
    return f.decrypt(raw).decode("utf-8")


def is_encrypted(value: str) -> bool:
    """判断值是否是 `enc:` 加密格式"""
    return bool(value) and value.startswith(_ENC_PREFIX)


def reset_cache_for_testing() -> None:
    """仅用于测试：清空主密钥缓存"""
    global _cached_key
    _cached_key = None
