# -*- coding: utf-8 -*-
"""effluent-06 红测丙：同口抢建必须抢口锁，后到只记争用痕且零行。

两路会话对同一个排放口（OF-E1-B / outfall:{id}）抢建批时：
- 口锁必须真实存在并串行化建批；
- 后到者拿不到口锁 -> 409，正式区零行；
- contention_log 必须留下 durable 的“争用失败”痕（不能随请求回滚被吞）。

修复前应见红：
1) locks.require_lock 在调用方事务里写 contention_log 后即 raise，
   插入随 with connect() 回滚，争用痕丢失；
2) 锁按 holder 可重入，同账号两路会话并发可双双建批（口锁对“会话”缺失）。
"""
from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import app
from db import init_db

DOWN_CODE = "OF-E1-B"


def _token(c: TestClient, user: str, pw: str) -> str:
    return c.post("/api/login", json={"username": user, "password": pw}).json()["token"]


def _h(tok: str) -> dict:
    return {"Authorization": "Bearer " + tok}


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    import db

    db_file = tmp_path / "outfall_down_c.db"
    monkeypatch.setattr(db, "DB_PATH", db_file)
    init_db()
    admin = TestClient(app)
    ah = _h(_token(admin, "admin", "admin123"))
    of = next(o for o in admin.get("/api/outfalls", headers=ah).json()["items"]
              if o["outfall_code"] == DOWN_CODE)

    def rows(sql, args=()):
        con = sqlite3.connect(db_file)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        finally:
            con.close()

    return {"db": db_file, "admin": admin, "ah": ah, "of": of, "rows": rows}


def _sample_body(of_id: int, code: str) -> dict:
    return {
        "outfall_id": of_id,
        "permit_ref": "DP-2026-E01",
        "sample_code": code,
        "flow_m3h": 120,
        "metrics": {"cod": 10.0, "nh3n": 1.0, "tp": 0.1},
    }


def test_race_outfall_create_loser_gets_409_and_durable_contention(ctx):
    """race_outfall_create：胜方持口锁，后到会话 409、零行、争用痕落库。"""
    admin, ah, of = ctx["admin"], ctx["ah"], ctx["of"]
    rows = ctx["rows"]
    lock_key = f"outfall:{of['id']}"

    # 胜方会话先把口锁稳稳持有（独立提交，对其它连接可见）。
    got = admin.post(f"/api/locks/acquire?lock_key={lock_key}", headers=ah)
    assert got.status_code == 200, got.text

    # 后到的第二路会话（writer）对同口抢建。
    writer = TestClient(app)
    wh = _h(_token(writer, "writer", "writer123"))
    resp = writer.post("/api/samples", headers=wh,
                       json=_sample_body(of["id"], "SM-RACE-C-01"))

    assert resp.status_code == 409, resp.text
    assert rows("SELECT COUNT(*) c FROM sample_batches WHERE sample_code='SM-RACE-C-01'")[0]["c"] == 0

    logs = admin.get("/api/locks", headers=ah).json()["contention"]
    hit = [x for x in logs if x.get("lock_key") == lock_key and x.get("action") == "争用失败"]
    assert hit, f"后到抢口锁必须留下 durable 争用痕，实际：{logs}"


def test_race_outfall_create_same_account_sessions_still_contend(ctx):
    """同账号两路会话也是两路会话：口锁按会话唯一，不得因 holder 相同而双建。

    用“胜方已持提交态口锁”确定性复现：同账号后到会话同样必须被口锁挡住。
    """
    admin, ah, of = ctx["admin"], ctx["ah"], ctx["of"]
    rows = ctx["rows"]
    lock_key = f"outfall:{of['id']}"
    assert admin.post(f"/api/locks/acquire?lock_key={lock_key}", headers=ah).status_code == 200

    second = TestClient(app)
    sh = _h(_token(second, "admin", "admin123"))
    resp = second.post("/api/samples", headers=sh,
                       json=_sample_body(of["id"], "SM-RACE-C-02"))
    assert resp.status_code == 409, "同 holder 不得重入另一路会话正在持有的口锁"
    assert rows("SELECT COUNT(*) c FROM sample_batches WHERE sample_code='SM-RACE-C-02'")[0]["c"] == 0


def test_race_outfall_create_parallel_double_request_single_official_row(ctx):
    """真·并发双请求打同口同编号：正式批至多一行，绝不双双 2xx。"""
    of = ctx["of"]
    db_file = ctx["db"]
    # 该不变量需要开放口（一路建成）；种子夹具预置 E1-B 停用，这里显式恢复。
    ctx["admin"].post(
        f"/api/outfalls/{of['id']}/status?status=开放", headers=ctx["ah"]
    )
    code = "SM-RACE-PARALLEL"
    barrier = threading.Barrier(2)

    def fire(_idx):
        c = TestClient(app)
        h = _h(_token(c, "admin", "admin123"))
        barrier.wait()
        r = c.post("/api/samples", headers=h, json=_sample_body(of["id"], code))
        return r.status_code

    with ThreadPoolExecutor(max_workers=2) as ex:
        statuses = list(ex.map(fire, [0, 1]))

    con = sqlite3.connect(db_file)
    try:
        n = con.execute("SELECT COUNT(*) FROM sample_batches WHERE sample_code=?", (code,)).fetchone()[0]
    finally:
        con.close()
    assert n == 1, f"同口同编号并发只能有一行正式批，实际 {n}（statuses={statuses}）"
    assert statuses.count(200) == 1, f"必须恰有一路建成，statuses={statuses}"
