"""
缓存系统
支持 Redis 和内存两级缓存，自动降级
"""
import asyncio
import json
import pickle
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, TypeVar

from .logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CacheBackend(ABC):
    """缓存后端接口"""

    @abstractmethod
    async def get(self, key: str, default: Any = None) -> Any: ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int = 300) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> bool: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def clear(self) -> None: ...


class MemoryCacheBackend(CacheBackend):
    """内存缓存后端 - 本地进程内缓存"""

    def __init__(self, default_ttl: int = 300):
        self._store: Dict[str, bytes] = {}
        self._ttl: Dict[str, float] = {}
        self._default_ttl = default_ttl
        self._cleanup_task: Optional[asyncio.Task] = None

    def _serialize(self, value: Any) -> bytes:
        return pickle.dumps(value)

    def _deserialize(self, data: bytes) -> Any:
        return pickle.loads(data)

    def _is_expired(self, key: str) -> bool:
        import time
        expiry = self._ttl.get(key)
        return expiry is not None and time.monotonic() > expiry

    async def get(self, key: str, default: Any = None) -> Any:
        if key not in self._store or self._is_expired(key):
            return default
        return self._deserialize(self._store[key])

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        import time
        resolved_ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = self._serialize(value)
        self._ttl[key] = time.monotonic() + resolved_ttl

    async def delete(self, key: str) -> bool:
        existed = key in self._store
        self._store.pop(key, None)
        self._ttl.pop(key, None)
        return existed

    async def exists(self, key: str) -> bool:
        return key in self._store and not self._is_expired(key)

    async def clear(self) -> None:
        self._store.clear()
        self._ttl.clear()


class RedisCacheBackend(CacheBackend):
    """Redis 缓存后端"""

    def __init__(self, redis_client: Any, default_ttl: int = 300, prefix: str = "cache:"):
        self._redis = redis_client
        self._default_ttl = default_ttl
        self._prefix = prefix
        self._fallback = MemoryCacheBackend(default_ttl)
        self._enabled = redis_client is not None

    def _make_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def get(self, key: str, default: Any = None) -> Any:
        if not self._enabled:
            return await self._fallback.get(key, default)
        try:
            data = await self._redis.get(self._make_key(key))
            if data is None:
                return default
            return json.loads(data)
        except Exception as e:
            logger.warning("Redis get failed, falling back to memory", key=key, error=str(e))
            return await self._fallback.get(key, default)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        resolved_ttl = ttl if ttl is not None else self._default_ttl
        if not self._enabled:
            await self._fallback.set(key, value, resolved_ttl)
            return
        try:
            serialized = json.dumps(value, ensure_ascii=False, default=str)
            await self._redis.setex(self._make_key(key), resolved_ttl, serialized)
        except Exception as e:
            logger.warning("Redis set failed, falling back to memory", key=key, error=str(e))
            await self._fallback.set(key, value, resolved_ttl)

    async def delete(self, key: str) -> bool:
        if not self._enabled:
            return await self._fallback.delete(key)
        try:
            result = await self._redis.delete(self._make_key(key))
            return result > 0
        except Exception as e:
            logger.warning("Redis delete failed", key=key, error=str(e))
            return await self._fallback.delete(key)

    async def exists(self, key: str) -> bool:
        if not self._enabled:
            return await self._fallback.exists(key)
        try:
            return bool(await self._redis.exists(self._make_key(key)))
        except Exception as e:
            logger.warning("Redis exists failed", key=key, error=str(e))
            return await self._fallback.exists(key)

    async def clear(self) -> None:
        if not self._enabled:
            await self._fallback.clear()
            return
        try:
            import redis.asyncio as redis_async
            cursor = 0
            pattern = f"{self._prefix}*"
            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("Redis clear failed", error=str(e))
            await self._fallback.clear()


class CacheService:
    """缓存服务 - 带装饰器、命名空间、自动降级"""

    def __init__(self, backend: CacheBackend):
        self._backend = backend
        self._namespace_separator = ":"

    async def get(self, key: str, default: Any = None) -> Any:
        return await self._backend.get(key, default)

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        await self._backend.set(key, value, ttl)

    async def delete(self, key: str) -> bool:
        return await self._backend.delete(key)

    async def exists(self, key: str) -> bool:
        return await self._backend.exists(key)

    async def clear(self) -> None:
        await self._backend.clear()

    def ns(self, namespace: str) -> "CacheService":
        """创建带命名空间的缓存实例"""
        wrapped = _NamespacedCache(self._backend, namespace, self._namespace_separator)
        svc = CacheService.__new__(CacheService)
        svc._backend = wrapped
        return svc

    @staticmethod
    def cached(ttl: int = 300, key_prefix: str = ""):
        """缓存装饰器 - 缓存函数返回值"""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            import functools
            @functools.wraps(func)
            async def wrapper(self_or_cls, *args, **kwargs):
                cache = getattr(self_or_cls, "_cache", None) if hasattr(self_or_cls, "_cache") else None
                if cache is None:
                    return await func(self_or_cls, *args, **kwargs)
                key_parts = [key_prefix, func.__name__]
                if args:
                    key_parts.append(str(args))
                if kwargs:
                    key_parts.append(str(sorted(kwargs.items())))
                cache_key = ":".join(key_parts)
                result = await cache.get(cache_key)
                if result is not None:
                    return result
                result = await func(self_or_cls, *args, **kwargs)
                await cache.set(cache_key, result, ttl)
                return result
            return wrapper
        return decorator


class _NamespacedCache(CacheBackend):
    """带命名空间的缓存后端代理"""

    def __init__(self, backend: CacheBackend, namespace: str, separator: str = ":"):
        self._backend = backend
        self._namespace = namespace
        self._separator = separator

    def _ns_key(self, key: str) -> str:
        return f"{self._namespace}{self._separator}{key}"

    async def get(self, key: str, default: Any = None) -> Any:
        return await self._backend.get(self._ns_key(key), default)

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        await self._backend.set(self._ns_key(key), value, ttl)

    async def delete(self, key: str) -> bool:
        return await self._backend.delete(self._ns_key(key))

    async def exists(self, key: str) -> bool:
        return await self._backend.exists(self._ns_key(key))

    async def clear(self) -> None:
        logger.warning("Namespace clear not supported, use root clear()", ns=self._namespace)


# ========== 工厂函数 ==========

def create_cache_service(redis_client: Optional[Any] = None, default_ttl: int = 300) -> CacheService:
    """创建缓存服务实例 - 自动选择后端"""
    if redis_client:
        backend = RedisCacheBackend(redis_client, default_ttl=default_ttl)
        logger.info("Cache initialized with Redis backend")
    else:
        backend = MemoryCacheBackend(default_ttl=default_ttl)
        logger.info("Cache initialized with in-memory backend")
    return CacheService(backend)


# 全局缓存实例（延迟初始化）
_cache_service: Optional[CacheService] = None


def get_cache() -> CacheService:
    """获取全局缓存实例"""
    global _cache_service
    if _cache_service is None:
        _cache_service = create_cache_service()
    return _cache_service
