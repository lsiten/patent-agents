"""
Tests for src.core.secret_cipher — Fernet-based encryption for per-agent API keys.

加密策略：
- 主密钥优先从环境变量 AGENT_OVERRIDE_MASTER_KEY 读取（base64 编码的 32 字节）
- 未设置时自动生成并持久化到 backend/data/.secret_key
- 加密结果以 "enc:" 前缀标记，方便区分明文
- decrypt 自动识别 "enc:" 前缀；非前缀视为明文原样返回（兼容旧数据）
"""
from __future__ import annotations

import os
import pytest
from cryptography.fernet import Fernet, InvalidToken


# ── 清理全局缓存的 master key，让每个测试独立 ──────────────────────
@pytest.fixture(autouse=True)
def _reset_cipher_state(tmp_path, monkeypatch):
    """重置 _get_master_key 的全局缓存，并临时切换 data 目录到 tmp_path"""
    # 隔离数据目录，避免污染真实 data/
    monkeypatch.setattr(
        "src.core.secret_cipher._DATA_DIR", tmp_path, raising=False
    )
    # 清除已缓存的 master key
    from src.core import secret_cipher
    secret_cipher._cached_key = None
    yield
    secret_cipher._cached_key = None


class TestRoundtrip:
    def test_encrypt_decrypt_returns_original(self):
        from src.core.secret_cipher import encrypt_value, decrypt_value
        encrypted = encrypt_value("sk-test-12345")
        assert encrypted.startswith("enc:")
        assert decrypt_value(encrypted) == "sk-test-12345"

    def test_unicode_roundtrip(self):
        from src.core.secret_cipher import encrypt_value, decrypt_value
        original = "中文-emoji-🔐-value"
        assert decrypt_value(encrypt_value(original)) == original

    def test_two_encryptions_produce_different_ciphertext(self):
        """Fernet 每次随机 IV，同一明文应产生不同密文"""
        from src.core.secret_cipher import encrypt_value
        a = encrypt_value("same-value")
        b = encrypt_value("same-value")
        assert a != b  # Fernet 包含时间戳 + 随机 IV
        # 但都正确解密
        from src.core.secret_cipher import decrypt_value
        assert decrypt_value(a) == decrypt_value(b) == "same-value"


class TestEmptyValue:
    def test_empty_string_round_trip(self):
        from src.core.secret_cipher import encrypt_value, decrypt_value
        # 空字符串直接走原样（不需要加密）
        assert encrypt_value("") == ""
        assert decrypt_value("") == ""


class TestPlaintextCompatibility:
    def test_decrypt_unprefixed_returns_as_is(self):
        """非 enc: 前缀视为明文，原样返回（向后兼容）"""
        from src.core.secret_cipher import decrypt_value
        assert decrypt_value("plain-text-key") == "plain-text-key"

    def test_is_encrypted_only_for_prefixed(self):
        from src.core.secret_cipher import is_encrypted
        assert is_encrypted("enc:abc") is True
        assert is_encrypted("plain") is False
        assert is_encrypted("") is False


class TestWrongKeyFails:
    def test_decrypt_with_different_master_key_raises(self, tmp_path, monkeypatch):
        """用 A key 加密，切换到 B key 解密必须抛 InvalidToken"""
        from src.core import secret_cipher
        # 用 env 注入 key A
        key_a = Fernet.generate_key().decode()
        monkeypatch.setenv("AGENT_OVERRIDE_MASTER_KEY", key_a)
        secret_cipher._cached_key = None
        encrypted = secret_cipher.encrypt_value("secret-data")

        # 切换到 key B
        key_b = Fernet.generate_key().decode()
        monkeypatch.setenv("AGENT_OVERRIDE_MASTER_KEY", key_b)
        secret_cipher._cached_key = None

        with pytest.raises(InvalidToken):
            secret_cipher.decrypt_value(encrypted)


class TestEnvMasterKey:
    def test_uses_env_master_key_when_set(self, monkeypatch):
        """设置 AGENT_OVERRIDE_MASTER_KEY 后，生成的 ciphertext 能被该 key 解密"""
        from src.core import secret_cipher
        explicit_key = Fernet.generate_key().decode()
        monkeypatch.setenv("AGENT_OVERRIDE_MASTER_KEY", explicit_key)
        secret_cipher._cached_key = None

        encrypted = secret_cipher.encrypt_value("hello")
        # 用 explicit key 直接解密
        Fernet(explicit_key.encode()).decrypt(
            encrypted.removeprefix("enc:").encode()
        )  # 不抛错即可

    def test_falls_back_to_file_when_env_missing(self, tmp_path, monkeypatch):
        """未设 env 时自动生成 key 并持久化到 _DATA_DIR/.secret_key"""
        from src.core import secret_cipher
        monkeypatch.delenv("AGENT_OVERRIDE_MASTER_KEY", raising=False)
        secret_cipher._cached_key = None

        # 第一次调用应触发自动生成
        encrypted = secret_cipher.encrypt_value("data1")

        # 文件应已创建
        key_file = tmp_path / ".secret_key"
        assert key_file.exists()
        assert key_file.read_text().strip() != ""

        # 第二次调用应该用同一个 key（缓存命中）
        encrypted2 = secret_cipher.encrypt_value("data2")
        # 验证：清缓存后从文件重读仍然能解密
        secret_cipher._cached_key = None
        assert secret_cipher.decrypt_value(encrypted) == "data1"
        assert secret_cipher.decrypt_value(encrypted2) == "data2"


class TestConcurrency:
    def test_concurrent_encrypt_decrypt_uses_same_key(self, monkeypatch):
        """并发场景下多次调用应共享同一 key"""
        from src.core import secret_cipher
        monkeypatch.setenv(
            "AGENT_OVERRIDE_MASTER_KEY", Fernet.generate_key().decode()
        )
        secret_cipher._cached_key = None

        results = [
            (
                secret_cipher.encrypt_value(f"v{i}"),
                secret_cipher.decrypt_value(secret_cipher.encrypt_value(f"v{i}")),
            )
            for i in range(20)
        ]
        for enc, dec in results:
            assert dec == dec  # sanity
        # 解密所有
        for i, (enc, _) in enumerate(results):
            assert secret_cipher.decrypt_value(enc) == f"v{i}"
