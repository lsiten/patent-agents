"""
Alembic 迁移环境 — 同步引擎用于迁移（开发 SQLite / 生产 PostgreSQL）
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

# 将 backend/ 加入 sys.path 以支持 from src.models import Base
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models import Base  # noqa: E402

# Alembic Config
config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Meta
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本而不连接数据库"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：使用同步引擎执行迁移"""
    url = config.get_main_option("sqlalchemy.url")
    url = url.replace("+aiosqlite", "").replace("+asyncpg", "")
    connectable = create_engine(url)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
