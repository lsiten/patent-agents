"""日期时间工具函数"""

import functools
import time
from datetime import datetime, timezone
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def utc_now() -> datetime:
    """获取当前 UTC 时间"""
    return datetime.now(timezone.utc)


def format_datetime(dt: datetime | None = None, fmt: str = "%Y-%m-%dT%H:%M:%SZ") -> str:
    """格式化日期时间为 ISO 风格字符串"""
    return (dt or utc_now()).strftime(fmt)


def timed(logger_call: Callable | None = None):
    """函数执行计时装饰器"""
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.monotonic()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.monotonic() - start
                log = logger_call or (lambda msg: None)
                log(f"{func.__name__} took {elapsed*1000:.1f}ms")
        return wrapper
    return decorator
