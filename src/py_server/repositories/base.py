"""事务边界与连接适配。

铁律：事务由 application 用例开启；repo 函数接受外部 conn，不自行开事务。
仅单表简单 CRUD 的便捷函数可内部 self-open（内部调用 with_conn）。
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .. import engine


@dataclass
class Row:
    """轻量 dict-like 行，兼容 `row["col"]` 与 `dict(row)` 两种用法。"""

    _data: dict[str, Any]

    def __getitem__(self, key) -> Any:
        if isinstance(key, int):
            return list(self._data.values())[key]
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def __iter__(self):
        return iter(self._data)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __repr__(self) -> str:
        return f"Row({self._data!r})"


class Result:
    def __init__(self, result: Any):
        self._result = result
        self.rowcount = result.rowcount
        self.lastrowid: int | None = None

    def fetchone(self) -> Row | None:
        row = self._result.fetchone()
        return Row(dict(row._mapping)) if row is not None else None

    def fetchall(self) -> list[Row]:
        return [Row(dict(row._mapping)) for row in self._result.fetchall()]


class Conn:
    """SQLAlchemy Connection 的薄适配层。

    - `execute(stmt, params)` 接受 SQLAlchemy Core 语句（推荐）。
    - `fetchone/fetchall` 返回 dict-like Row，兼容 `row["col"]` / `dict(row)`。
    - `lastrowid`：本次 INSERT 的自增主键（通过 inserted_primary_key 读取）。
    """

    def __init__(self, conn: Connection):
        self._conn = conn
        self.lastrowid: int | None = None

    def execute(self, statement: Any, params: Any = None):
        # 兼容测试夹具中临时构造数据的原生 SQL 字符串（生产代码只用 SQLAlchemy Core）。
        if isinstance(statement, str):
            statement = text(statement)
            if params is not None and not isinstance(params, dict):
                # SQLAlchemy 2.x text() 需要具名参数；把 `?` 占位符转成 :p0/:p1 ...
                names = {}
                sql = statement.text
                for i, value in enumerate(params):
                    name = f"p{i}"
                    names[name] = value
                    sql = sql.replace("?", f":{name}", 1)
                statement = text(sql)
                params = names
        result = (
            self._conn.execute(statement, params)
            if params is not None
            else self._conn.execute(statement)
        )
        if result.is_insert:
            try:
                pk = result.inserted_primary_key
                self.lastrowid = int(pk[0]) if pk and pk[0] is not None else None
            except (AttributeError, NotImplementedError, Exception):
                # executemany 不支持 inserted_primary_key；不影响调用方。
                self.lastrowid = None
        return Result(result)

    def commit(self) -> None:
        # 事务由 with_conn 统一管理；保留接口兼容旧调用。
        pass

    def rollback(self) -> None:
        pass


@contextmanager
def with_conn() -> Iterator[Conn]:
    """开启事务：正常退出提交，异常回滚。"""
    with engine.get_engine().connect() as raw:
        with raw.begin():
            yield Conn(raw)


@contextmanager
def with_read_conn() -> Iterator[Conn]:
    """只读连接，不显式开启事务。"""
    with engine.get_engine().connect() as raw:
        yield Conn(raw)


@contextmanager
def _tx() -> Iterator[Conn]:
    """兼容旧 services 内部使用的别名。"""
    with with_conn() as conn:
        yield conn


def rows_to_dicts(rows: list[Row]) -> list[dict]:
    return [dict(row) for row in rows]

def dialect_insert(table):
    """返回支持 ON CONFLICT 的 Insert 构造器，按当前 Engine 方言选择。

    这样 upsert 语句仍是 SQLAlchemy Core 构造，不做方言特有字符串拼接，
    切换 PostgreSQL 时只需更换 Engine，repo 代码不变。
    """
    from sqlalchemy.dialects import postgresql, sqlite
    name = engine.get_engine().dialect.name
    if name == "postgresql":
        return postgresql.insert(table)
    return sqlite.insert(table)
