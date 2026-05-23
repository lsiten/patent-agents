"""
文件存储抽象层
支持本地文件系统和 MinIO/S3 两种存储后端
"""
import io
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, List, Optional, Tuple
from urllib.parse import urlparse

from .config import settings
from .logging import get_logger

logger = get_logger(__name__)


class StorageBackend(ABC):
    """存储后端接口"""

    @abstractmethod
    async def save(self, path: str, content: bytes) -> str: ...

    @abstractmethod
    async def load(self, path: str) -> Optional[bytes]: ...

    @abstractmethod
    async def delete(self, path: str) -> bool: ...

    @abstractmethod
    async def exists(self, path: str) -> bool: ...

    @abstractmethod
    async def list(self, prefix: str) -> List[str]: ...

    @abstractmethod
    async def size(self, path: str) -> Optional[int]: ...

    @abstractmethod
    def get_url(self, path: str) -> str: ...


class LocalStorageBackend(StorageBackend):
    """本地文件系统存储后端"""

    def __init__(self, base_path: str = "./storage"):
        self._base = Path(base_path).resolve()
        self._base.mkdir(parents=True, exist_ok=True)
        logger.info("Local storage initialized", base_path=str(self._base))

    def _resolve(self, path: str) -> Path:
        full = self._base / path
        full.parent.mkdir(parents=True, exist_ok=True)
        return full

    async def save(self, path: str, content: bytes) -> str:
        target = self._resolve(path)
        target.write_bytes(content)
        logger.debug("File saved", path=str(target), size=len(content))
        return str(target)

    async def load(self, path: str) -> Optional[bytes]:
        target = self._base / path
        if not target.exists():
            return None
        return target.read_bytes()

    async def delete(self, path: str) -> bool:
        target = self._base / path
        if not target.exists():
            return False
        target.unlink()
        logger.debug("File deleted", path=path)
        return True

    async def exists(self, path: str) -> bool:
        return (self._base / path).exists()

    async def list(self, prefix: str) -> List[str]:
        search_dir = self._base / prefix
        if not search_dir.exists():
            return []
        return [
            str(p.relative_to(self._base))
            for p in search_dir.rglob("*")
            if p.is_file()
        ]

    async def size(self, path: str) -> Optional[int]:
        target = self._base / path
        if not target.exists():
            return None
        return target.stat().st_size

    def get_url(self, path: str) -> str:
        return str(self._base / path)


class MinioStorageBackend(StorageBackend):
    """MinIO/S3 对象存储后端"""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = True,
        public_base_url: Optional[str] = None,
    ):
        self._endpoint = endpoint
        self._bucket = bucket
        self._secure = secure
        self._public_base_url = public_base_url
        self._client = None
        self._enabled = bool(endpoint and access_key and secret_key)
        self._init_client(access_key, secret_key)

    def _init_client(self, access_key: str, secret_key: str) -> None:
        if not self._enabled:
            logger.warning("MinIO not configured, skipping")
            return
        try:
            from minio import Minio
            self._client = Minio(
                self._endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=self._secure,
            )
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
            logger.info("MinIO storage initialized", endpoint=self._endpoint, bucket=self._bucket)
        except ImportError:
            logger.warning("minio package not installed, falling back")
            self._enabled = False
        except Exception as e:
            logger.error("MinIO initialization failed", error=str(e))
            self._enabled = False

    async def save(self, path: str, content: bytes) -> str:
        if not self._enabled:
            raise RuntimeError("MinIO not available")
        from minio.commonconfig import COMPLIANCE
        stream = io.BytesIO(content)
        length = len(content)
        self._client.put_object(self._bucket, path, stream, length)
        logger.debug("Object saved", bucket=self._bucket, path=path, size=length)
        return path

    async def load(self, path: str) -> Optional[bytes]:
        if not self._enabled:
            return None
        try:
            response = self._client.get_object(self._bucket, path)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except Exception as e:
            logger.warning("Object load failed", path=path, error=str(e))
            return None

    async def delete(self, path: str) -> bool:
        if not self._enabled:
            return False
        try:
            self._client.remove_object(self._bucket, path)
            return True
        except Exception as e:
            logger.warning("Object delete failed", path=path, error=str(e))
            return False

    async def exists(self, path: str) -> bool:
        if not self._enabled:
            return False
        try:
            self._client.stat_object(self._bucket, path)
            return True
        except Exception:
            return False

    async def list(self, prefix: str) -> List[str]:
        if not self._enabled:
            return []
        try:
            objects = self._client.list_objects(self._bucket, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects]
        except Exception as e:
            logger.warning("Object list failed", prefix=prefix, error=str(e))
            return []

    async def size(self, path: str) -> Optional[int]:
        if not self._enabled:
            return None
        try:
            stat = self._client.stat_object(self._bucket, path)
            return stat.size
        except Exception:
            return None

    def get_url(self, path: str) -> str:
        if self._public_base_url:
            return f"{self._public_base_url}/{path}"
        protocol = "https" if self._secure else "http"
        return f"{protocol}://{self._endpoint}/{self._bucket}/{path}"


class StorageService:
    """文件存储服务 - 统一接口"""

    def __init__(self, backend: StorageBackend):
        self._backend = backend

    async def save(self, path: str, content: bytes) -> str:
        return await self._backend.save(path, content)

    async def save_text(self, path: str, text: str, encoding: str = "utf-8") -> str:
        return await self._backend.save(path, text.encode(encoding))

    async def load(self, path: str) -> Optional[bytes]:
        return await self._backend.load(path)

    async def load_text(self, path: str, encoding: str = "utf-8") -> Optional[str]:
        data = await self._backend.load(path)
        return data.decode(encoding) if data else None

    async def delete(self, path: str) -> bool:
        return await self._backend.delete(path)

    async def exists(self, path: str) -> bool:
        return await self._backend.exists(path)

    async def list(self, prefix: str = "") -> List[str]:
        return await self._backend.list(prefix)

    async def size(self, path: str) -> Optional[int]:
        return await self._backend.size(path)

    def get_url(self, path: str) -> str:
        return self._backend.get_url(path)


# ========== 工厂函数 ==========

def create_storage_service() -> StorageService:
    """创建存储服务实例 - 优先使用 MinIO"""
    if settings.storage and settings.storage.minio_endpoint:
        logger.info("Initializing MinIO storage")
        backend = MinioStorageBackend(
            endpoint=settings.storage.minio_endpoint,
            access_key=settings.storage.minio_access_key,
            secret_key=settings.storage.minio_secret_key,
            bucket=settings.storage.minio_bucket,
            secure=settings.storage.minio_secure,
        )
        if backend._enabled:
            return StorageService(backend)
    logger.info("Falling back to local storage")
    backend = LocalStorageBackend(base_path=settings.storage.export_path)
    return StorageService(backend)


# 全局存储实例（延迟初始化）
_storage_service: Optional[StorageService] = None


def get_storage() -> StorageService:
    """获取全局存储实例"""
    global _storage_service
    if _storage_service is None:
        _storage_service = create_storage_service()
    return _storage_service
