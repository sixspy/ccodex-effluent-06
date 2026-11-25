"""排放批争用锁。

effluent-06 停用禁采：口锁按“会话持锁令牌”唯一，同账号两路会话也是两路
会话，不得因 holder 相同而重入另一路正在持有的 outfall 口锁。争用痕必须
在独立连接里提交，确保后到者请求事务回滚时“争用失败”痕不被吞掉。
"""
from __future__ import annotations

import sqlite3
import uuid

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit

router = APIRouter(tags=["locks"])

CONTENTION_ACTION = "争用失败"


def record_contention_durable(
    lock_key: str, actor: str, detail: str | None = None, action: str = CONTENTION_ACTION
) -> None:
    """争用痕另笔提交，独立于调用方可能整体回滚的业务事务。"""
    with connect() as conn:
        conn.execute(
            """INSERT INTO contention_log(lock_key,actor,action,detail,created_at)
               VALUES (?,?,?,?,?)""",
            (lock_key, actor, action, detail, now_iso()),
        )
        conn.commit()


def require_lock(conn, lock_key: str, holder: str) -> None:
    """旧调用方（sample/exceed 锁）使用的 holder 可重入锁。

    保留同 holder 重入语义以兼容既有流程；冲突时把争用痕 durable 落库，
    不再随调用方事务回滚丢失。
    """
    row = conn.execute(
        "SELECT holder FROM effluent_locks WHERE lock_key=?", (lock_key,)
    ).fetchone()
    if row and row["holder"] != holder:
        record_contention_durable(
            lock_key, holder, f"持有人={row['holder']}"
        )
        raise HTTPException(409, f"锁被占用：{lock_key} 持有人 {row['holder']}")
    if not row:
        try:
            conn.execute(
                "INSERT INTO effluent_locks(lock_key,holder,acquired_at) VALUES (?,?,?)",
                (lock_key, holder, now_iso()),
            )
        except sqlite3.IntegrityError as exc:
            raced = conn.execute(
                "SELECT holder FROM effluent_locks WHERE lock_key=?", (lock_key,)
            ).fetchone()
            owner = raced["holder"] if raced else "未知"
            record_contention_durable(lock_key, holder, f"持有人={owner}")
            raise HTTPException(409, f"锁被占用：{lock_key} 持有人 {owner}") from exc


def acquire_session_lock(lock_key: str, holder: str) -> str:
    """effluent-06：会话级不可重入口锁，抢不到即记争用痕并 409。

    锁行立即独立提交，使其在整个临界区对其它连接可见；插入以 lock_key
    主键做原子仲裁，杜绝 check-then-insert 的 TOCTOU 双持。
    返回仅本会话持有的 owner_token，释放时必须凭它删除。
    """
    token = f"{holder}:{uuid.uuid4().hex}"
    conn = connect()
    try:
        try:
            conn.execute(
                """INSERT INTO effluent_locks(lock_key,holder,owner_token,acquired_at)
                   VALUES (?,?,?,?)""",
                (lock_key, holder, token, now_iso()),
            )
            conn.commit()
            return token
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            row = conn.execute(
                "SELECT holder FROM effluent_locks WHERE lock_key=?", (lock_key,)
            ).fetchone()
            owner = row["holder"] if row else "未知"
            record_contention_durable(
                lock_key, holder, f"持有人={owner}；后到会话抢口锁失败"
            )
            raise HTTPException(
                409, f"口锁被占用：{lock_key} 持有人 {owner}，后到只记争用痕"
            ) from exc
        except sqlite3.OperationalError as exc:  # database is locked / busy
            conn.rollback()
            record_contention_durable(lock_key, holder, "口锁忙，仲裁超时")
            raise HTTPException(409, f"口锁忙：{lock_key}，请败方零行重试") from exc
    finally:
        conn.close()


def release_session_lock(lock_key: str, token: str) -> None:
    """凭会话 token 释放口锁；只删自己持有的那一行。"""
    if not token:
        return
    with connect() as conn:
        conn.execute(
            "DELETE FROM effluent_locks WHERE lock_key=? AND owner_token=?",
            (lock_key, token),
        )
        conn.commit()


def release(conn, lock_key: str, holder: str) -> None:
    conn.execute(
        "DELETE FROM effluent_locks WHERE lock_key=? AND holder=?",
        (lock_key, holder),
    )


@router.get("/api/locks")
def list_locks(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        locks = [dict(r) for r in conn.execute("SELECT * FROM effluent_locks").fetchall()]
        logs = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM contention_log ORDER BY id DESC LIMIT 50"
            ).fetchall()
        ]
        return {"locks": locks, "contention": logs}


@router.post("/api/locks/acquire")
def acquire(lock_key: str, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        require_lock(conn, lock_key, user)
        write_audit(conn, user, "lock_acquire", lock_key, {})
        conn.commit()
        return {"ok": True, "lock_key": lock_key, "holder": user}


@router.post("/api/locks/release")
def release_api(lock_key: str, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        release(conn, lock_key, user)
        write_audit(conn, user, "lock_release", lock_key, {})
        conn.commit()
        return {"ok": True}
