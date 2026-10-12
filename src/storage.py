# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 存储层
===================================

职责：
1. 管理 SQLite 数据库连接（单例模式）
2. 定义 ORM 数据模型
3. 提供数据存取接口
4. 实现智能更新逻辑（断点续传）
"""

import atexit
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Optional, TypeVar

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Float,
    DateTime,
    Integer,
    Text,
    event,
    inspect,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    Session,
)
from sqlalchemy.exc import IntegrityError

from src.config import get_config

logger = logging.getLogger(__name__)
T = TypeVar("T")
CURRENT_SCHEMA_VERSION = "2026-06-05-create-all-baseline"

#: The page's vocabulary reached the database (owner decision
#: 2026-09-24): the run and transcript tables now name their columns as
#: the analysis page names the facts (ticker, risk_pct, reward_ratio,
#: max_hold_weeks, run_id; call_number, llm, time_ms, input, output…),
#: risk is stored as a percent, and the stored report uses the same
#: words. Runs stored before that were test runs (owner decision), so a
#: database still carrying the old columns has its run and transcript
#: tables dropped and recreated empty at startup rather than migrated;
#: this version string in schema_migrations marks that it happened.
VOCABULARY_RESET_VERSION = "2026-09-24-page-vocabulary"
#: A column each old-shaped table carried and the new shape does not:
#: seeing it means the table predates the vocabulary change.
LEGACY_COLUMN_MARKERS: Dict[str, str] = {
    "tiered_runs": "task_id",
    "tiered_run_transcripts": "task_id",
}

# SQLAlchemy ORM 基类
Base = declarative_base()


def utc_naive_now() -> datetime:
    """Return current UTC time without tzinfo for SQLite DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive_datetime(value: datetime) -> datetime:
    """Normalize aware datetimes to UTC-naive; treat naive values as UTC-naive."""
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def utc_iso(value: Optional[datetime]) -> Optional[str]:
    """A stored (UTC-naive) time as ISO 8601 with its ``+00:00`` offset
    spelled out, so a reader — the page, or the model reading a tool
    result next to offset-bearing clocks — never has to guess the zone
    (2026-10-10). None stays None."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


# === 数据模型定义 ===

class DatabaseSchemaMigration(Base):
    """Applied database schema version marker."""

    __tablename__ = 'schema_migrations'

    version = Column(String(64), primary_key=True)
    description = Column(String(255), nullable=False)
    applied_at = Column(DateTime, default=datetime.now, nullable=False, index=True)


class TieredRunRecord(Base):
    """One tiered-analysis run (src/tiered_analysis): status + full report.

    The analysis page lists these as its run history; result_json holds
    the serialized report (data reports, levels, outlook) so revisiting
    a finished run needs no re-analysis. Every column is named as the
    analysis page names the fact (owner request 2026-09-24).
    """

    __tablename__ = 'tiered_runs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, unique=True, index=True)
    ticker = Column(String(16), nullable=False, index=True)
    status = Column(String(16), nullable=False, default='running', index=True)
    result_json = Column(Text)
    #: The run's inputs (capital, risk_pct, reward_ratio, max_hold_weeks,
    #: tier) as JSON, recorded at creation so history rows can show them
    #: while the run is still in flight (owner decision 2026-07-24).
    inputs_json = Column(Text)
    error = Column(Text)
    created_at = Column(DateTime, default=utc_naive_now, index=True)
    updated_at = Column(DateTime, default=utc_naive_now, onupdate=utc_naive_now, index=True)
    #: The run-list facts as real columns (2026-09-21), so the list
    #: endpoint can filter and page in SQL instead of shipping every row
    #: for the browser to sift. Written from the inputs at creation and
    #: from the report at completion; see src/tiered_analysis/run_digest.
    capital = Column(Float)
    #: Percent of capital risked (1 = 1%), as the form takes it.
    risk_pct = Column(Float)
    reward_ratio = Column(Float)
    max_hold_weeks = Column(Integer)
    tier = Column(Integer, index=True)
    outlook = Column(String(16), index=True)
    #: Float: some markets size in fractional units.
    shares = Column(Float)


class TieredRunTranscriptRecord(Base):
    """One LLM call of one tiered run (src/tiered_analysis/llm_support).

    A run's transcript is the list of its rows ordered by ``call_number``:
    the stage of the run, the llm, the full input, the raw output, token
    counts, and the error when the call itself failed. Kept in its own
    table (not on the run row) so the history list stays light; rows
    older than ``history.TRANSCRIPT_MAX_AGE_DAYS`` are pruned at startup.
    """

    __tablename__ = 'tiered_run_transcripts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, index=True)
    call_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utc_naive_now, index=True)
    stage = Column(String(64))
    llm = Column(String(128))
    temperature = Column(Float)
    time_ms = Column(Integer)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    #: Which reply enforcement was requested: "schema", "json", or None.
    structured = Column(String(16))
    error = Column(Text)
    input = Column(Text)
    output = Column(Text)


class TieredCacheRecord(Base):
    """Fetched-data cache (src/tiered_analysis/cache_store): a JSON value
    per key. Safe to wipe — every row can be refetched from its vendor."""

    __tablename__ = 'tiered_cache'

    key = Column(String(255), primary_key=True)
    value_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=utc_naive_now, onupdate=utc_naive_now, index=True)


class ChatConversationRecord(Base):
    """One chat conversation (src/chat, 2026-09-21): a title and,
    while the bot waits for the user's yes or no on an action, the tool
    calls being held (``pending_json``). The messages are the rows of
    ChatMessageRecord in ``seq`` order."""

    __tablename__ = 'chat_conversations'

    id = Column(String(64), primary_key=True)
    title = Column(String(120))
    created_at = Column(DateTime, default=utc_naive_now, index=True)
    updated_at = Column(DateTime, default=utc_naive_now, onupdate=utc_naive_now, index=True)
    pending_json = Column(Text)


class ChatMessageRecord(Base):
    """One message of a chat conversation, stored in the shape the
    model exchange uses (``content_json``: role, text, the tool calls the
    model asked for, or one tool's result) plus the facts the chat page
    shows beside it (token usage, sizes, errors). The bot's own memory
    is exactly these rows, so a conversation survives a restart."""

    __tablename__ = 'chat_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(64), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    #: user, assistant, or tool.
    role = Column(String(16), nullable=False)
    content_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_naive_now)
    #: The model call's token counts, copied out of ``content_json`` on
    #: write (0 on rows that hold no call), so the conversation list can
    #: sum them in SQL instead of parsing every stored prompt on every
    #: sidebar refresh (2026-10-10). NULL only on rows written before
    #: the columns existed; startup backfills those once.
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)


class _DatabaseManagerMeta(type):
    """Serialize DatabaseManager construction across __new__ and __init__."""

    def __call__(cls, *args, **kwargs):
        with cls._init_lock:
            return super().__call__(*args, **kwargs)


class DatabaseManager(metaclass=_DatabaseManagerMeta):
    """
    数据库管理器 - 单例模式

    职责：
    1. 管理数据库连接池
    2. 提供 Session 上下文管理
    3. 封装数据存取操作
    """

    _instance: Optional['DatabaseManager'] = None
    _init_lock = threading.RLock()
    _initialized: bool = False

    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_url: Optional[str] = None):
        """
        初始化数据库管理器

        Args:
            db_url: 数据库连接 URL（可选，默认从配置读取）
        """
        if getattr(self, '_initialized', False):
            return

        created_engine = None

        try:
            config = get_config()
            if db_url is None:
                db_url = config.get_db_url()

            self._db_url = db_url
            self._sqlite_wal_enabled = config.sqlite_wal_enabled
            self._sqlite_busy_timeout_ms = config.sqlite_busy_timeout_ms

            engine_kwargs = {
                "echo": False,
                "pool_pre_ping": True,
            }
            if str(db_url).startswith("sqlite:") and self._sqlite_busy_timeout_ms > 0:
                engine_kwargs["connect_args"] = {
                    "timeout": self._sqlite_busy_timeout_ms / 1000,
                }

            # 创建数据库引擎
            created_engine = create_engine(
                db_url,
                **engine_kwargs,
            )
            self._engine = created_engine
            self._is_sqlite_engine = self._engine.url.get_backend_name() == 'sqlite'
            self._sqlite_file_db = self._is_sqlite_engine and self._is_file_sqlite_database()
            self._install_sqlite_pragma_handler()

            # 创建 Session 工厂
            self._SessionLocal = sessionmaker(
                bind=self._engine,
                autocommit=False,
                autoflush=False,
            )

            # Tables from before the page-vocabulary change go first,
            # then every table is (re)created.
            self._reset_legacy_tables()
            Base.metadata.create_all(self._engine)
            self._add_missing_columns()
            self._ensure_schema_migration_record()

            self._initialized = True
            logger.info(f"数据库初始化完成: {db_url}")

            # 注册退出钩子，确保程序退出时关闭数据库连接
            atexit.register(DatabaseManager._cleanup_engine, self._engine)
        except Exception:
            self._initialized = False
            try:
                if created_engine is not None:
                    created_engine.dispose()
            except Exception as cleanup_exc:
                logger.warning("数据库初始化失败后的引擎清理也失败: %s", cleanup_exc)
            self._engine = None
            self._SessionLocal = None
            self.__class__._instance = None
            raise

    def _ensure_schema_migration_record(self) -> None:
        session = self._SessionLocal()
        values = {
            "version": CURRENT_SCHEMA_VERSION,
            "description": "Baseline schema created through SQLAlchemy metadata.create_all",
        }
        try:
            if self._is_sqlite_engine:
                statement = sqlite_insert(DatabaseSchemaMigration).values(**values)
                statement = statement.on_conflict_do_nothing(index_elements=["version"])
                session.execute(statement)
            else:
                session.execute(DatabaseSchemaMigration.__table__.insert().values(**values))
            session.commit()
        except IntegrityError:
            session.rollback()
            with self._SessionLocal() as verify_session:
                existing = verify_session.get(DatabaseSchemaMigration, CURRENT_SCHEMA_VERSION)
            if existing is None:
                raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _add_missing_columns(self) -> None:
        """Add, in place, the columns a model gained after the database
        was created (2026-10-10: the chat token counts). ``create_all``
        makes missing tables but never touches an existing one, so each
        mapped table is compared with the live one and every column it
        lacks is added with ``ALTER TABLE ... ADD COLUMN``, which sqlite
        and Postgres both take for a nullable column without a default.
        A column that could not be added that way (NOT NULL, a key) is
        only logged. The names come from our own models, never from
        input. A failure is logged and leaves the table as it was — the
        app then fails loudly on its first query of that column rather
        than quietly misreading rows."""
        try:
            inspector = inspect(self._engine)
            existing = set(inspector.get_table_names())
            with self._engine.begin() as connection:
                for table in Base.metadata.sorted_tables:
                    if table.name not in existing:
                        continue
                    live = {col["name"] for col in inspector.get_columns(table.name)}
                    for column in table.columns:
                        if column.name in live:
                            continue
                        if column.primary_key or not column.nullable:
                            logger.warning(
                                "column %s.%s is missing and cannot be added in place",
                                table.name, column.name,
                            )
                            continue
                        column_type = column.type.compile(dialect=self._engine.dialect)
                        connection.exec_driver_sql(
                            f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column_type}"
                        )
                        logger.warning("added column %s.%s to an older database", table.name, column.name)
        except Exception as exc:
            logger.warning("adding missing columns skipped: %s", exc)

    def _reset_legacy_tables(self) -> None:
        """Drop the run and transcript tables of a database created before
        the page-vocabulary change (``LEGACY_COLUMN_MARKERS``), so
        ``create_all`` recreates them in the new shape. Old runs were test
        runs (owner decision 2026-09-24) and are not carried over; the
        chat tables and the fetched-data cache are untouched. Logged, and
        recorded once in schema_migrations. A failure here only leaves
        the old tables in place — the app then fails loudly on its first
        query rather than silently misreading old rows."""
        try:
            inspector = inspect(self._engine)
            existing = set(inspector.get_table_names())
            legacy = [
                table for table, marker in LEGACY_COLUMN_MARKERS.items()
                if table in existing
                and marker in {col["name"] for col in inspector.get_columns(table)}
            ]
            if not legacy:
                return
            with self._engine.begin() as connection:
                for table in legacy:
                    connection.exec_driver_sql(f"DROP TABLE {table}")
            logger.warning(
                "dropped %s: stored before the page-vocabulary change "
                "(old runs were test runs and are not carried over)",
                ", ".join(legacy),
            )
        except Exception as exc:
            logger.warning("legacy table reset skipped: %s", exc)
            return
        Base.metadata.create_all(self._engine)
        session = self._SessionLocal()
        try:
            if session.get(DatabaseSchemaMigration, VOCABULARY_RESET_VERSION) is None:
                session.add(DatabaseSchemaMigration(
                    version=VOCABULARY_RESET_VERSION,
                    description="Run and transcript tables recreated with the analysis page's column names",
                ))
                session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    @classmethod
    def get_instance(cls) -> 'DatabaseManager':
        """获取单例实例"""
        with cls._init_lock:
            if cls._instance is None:
                cls()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于测试）"""
        with cls._init_lock:
            if cls._instance is not None:
                if hasattr(cls._instance, '_engine') and cls._instance._engine is not None:
                    cls._instance._engine.dispose()
                cls._instance._initialized = False
                cls._instance = None

    @classmethod
    def _cleanup_engine(cls, engine) -> None:
        """
        清理数据库引擎（atexit 钩子）

        确保程序退出时关闭所有数据库连接，避免 ResourceWarning

        Args:
            engine: SQLAlchemy 引擎对象
        """
        try:
            if engine is not None:
                engine.dispose()
                logger.debug("数据库引擎已清理")
        except Exception as e:
            logger.warning(f"清理数据库引擎时出错: {e}")

    def _install_sqlite_pragma_handler(self) -> None:
        """为 SQLite 连接安装竞争保护参数。"""
        if not self._is_sqlite_engine:
            return

        @event.listens_for(self._engine, "connect")
        def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(f"PRAGMA busy_timeout={int(self._sqlite_busy_timeout_ms)}")
                if self._sqlite_file_db and self._sqlite_wal_enabled:
                    cursor.execute("PRAGMA journal_mode=WAL")
            except Exception as exc:
                logger.warning("初始化 SQLite PRAGMA 失败: %s", exc)
            finally:
                cursor.close()

    def _upsert_insert(self, model):
        """An INSERT that supports ``on_conflict_do_update`` on the
        engine in use — sqlite by default, Postgres under DATABASE_URL."""
        return sqlite_insert(model) if self._is_sqlite_engine else pg_insert(model)

    def _is_file_sqlite_database(self) -> bool:
        database = (self._engine.url.database or "").strip()
        return bool(database) and database.lower() != ":memory:"

    def get_session(self) -> Session:
        """
        获取数据库 Session

        使用示例:
            with db.get_session() as session:
                # 执行查询
                session.commit()  # 如果需要
        """
        if not getattr(self, '_initialized', False) or not hasattr(self, '_SessionLocal'):
            raise RuntimeError(
                "DatabaseManager 未正确初始化。"
                "请确保通过 DatabaseManager.get_instance() 获取实例。"
            )
        session = self._SessionLocal()
        try:
            return session
        except Exception:
            session.close()
            raise
