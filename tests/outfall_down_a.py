# -*- coding: utf-8 -*-
"""effluent-06 红测甲：停用排放口不得出正式采样批。

正确性口径（甲路径）：排放口一旦停用，采样写口必须零增、整笔回退；
唯一允许落库的是另笔提交的“停用禁采偏航”裁决痕。正式区 sample_batches
不得出现 SM-F03。

本文件在修复前应见红：种子里虽有一道单点 validate_outfall_open 的 400
（表面假绿），但没有 durable 的停用禁采裁决/偏航痕，也没有与口锁、
停用态联动的整笔回退保证。
"""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import app
from db import init_db

DOWN_CODE = "OF-E1-B"
OFFICIAL_BATCH = "SM-F03"
RULING_DATE = "2026-11-25"


def _auth(c: TestClient, user: str = "admin", password: str = "admin123") -> dict:
    tok = c.post(
        "/api/login", json={"username": user, "password": password}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


@pytest.fixture()
def down_ctx(tmp_path, monkeypatch):
    """停用口预置夹具：独立临时库 + 把 OF-E1-B 预置为停用。"""
    import db

    db_file = tmp_path / "outfall_down_a.db"
    monkeypatch.setattr(db, "DB_PATH", db_file)
    init_db()
    c = TestClient(app)
    h = _auth(c)
    row = c.post(
        "/api/login", json={"username": "admin", "password": "admin123"}
    ).json()
    outfalls = c.get("/api/outfalls", headers=h).json()["items"]
    of = next(o for o in outfalls if o["outfall_code"] == DOWN_CODE)
    resp = c.post(f"/api/outfalls/{of['id']}/status?status=停用", headers=h)
    assert resp.status_code == 200, resp.text

    def db_rows(sql: str, args=()):
        con = sqlite3.connect(db_file)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        finally:
            con.close()

    yield {"c": c, "h": h, "of": of, "db_file": db_file, "rows": db_rows}


def _payload(code: str | None = OFFICIAL_BATCH) -> dict:
    return {
        "outfall_id": 2,  # OF-E1-B 在种子库固定为 id=2，夹具里再用 of['id'] 覆盖
        "permit_ref": "DP-2026-E01",
        "sample_code": code,
        "flow_m3h": 1200,
        "metrics": {"cod": 31.0, "nh3n": 2.4, "tp": 0.19},
    }


def test_a0_fixture_pre_disables_of_e1_b(down_ctx):
    """预置夹具必须真的把 OF-E1-B 置成停用（排放口服务同源状态）。"""
    of = down_ctx["of"]
    latest = next(
        o
        for o in down_ctx["c"].get("/api/outfalls", headers=down_ctx["h"])
        .json()["items"]
        if o["id"] == of["id"]
    )
    assert latest["status"] == "停用"


def test_outfall_down_a_locked_no_official_batch_sm_f03(down_ctx):
    """甲断言：停用口仍（被挡住不得）出正式采样 SM-F03，零增且整笔回退。"""
    c, h, of = down_ctx["c"], down_ctx["h"], down_ctx["of"]
    rows = down_ctx["rows"]
    payload = _payload()
    payload["outfall_id"] = of["id"]

    before = rows(
        "SELECT COUNT(*) c FROM sample_batches WHERE outfall_id=?", (of["id"],)
    )[0]["c"]

    resp = c.post("/api/samples", headers=h, json=payload)

    # 必须拒写：停用态不可采样（保留种子既有 400 口径）。
    assert resp.status_code in (400, 409), resp.text
    detail = resp.json().get("detail", "")
    assert "停用" in detail or "禁采" in detail

    # 正式区零增：SM-F03 不得出现在 sample_batches。
    assert rows(
        "SELECT COUNT(*) c FROM sample_batches WHERE sample_code=?",
        (OFFICIAL_BATCH,),
    )[0]["c"] == 0
    after = rows(
        "SELECT COUNT(*) c FROM sample_batches WHERE outfall_id=?", (of["id"],)
    )[0]["c"]
    assert after == before, "停用口采样被拒后该口正式批行数必须零增"

    # 整笔回退：不得残留未释放的 outfall 口锁。
    leftover = rows(
        "SELECT COUNT(*) c FROM effluent_locks WHERE lock_key=?",
        (f"outfall:{of['id']}",),
    )[0]["c"]
    assert leftover == 0, "拒写回退后口锁不得残留"


def test_outfall_down_a_records_durable_deviation_ruling(down_ctx):
    """偏离裁决：强写停用口必须另笔留下 durable 的“停用禁采偏航”痕。"""
    c, h, of = down_ctx["c"], down_ctx["h"], down_ctx["of"]
    payload = _payload()
    payload["outfall_id"] = of["id"]
    resp = c.post("/api/samples", headers=h, json=payload)
    assert resp.status_code in (400, 409)

    audits = c.get("/api/audit?limit=500", headers=h).json()["items"]
    markers = [a for a in audits if a.get("action") == "停用禁采偏航"]
    assert markers, "停用口强写必须记一条 action=停用禁采偏航 的审计/裁决痕"
    target_blob = " ".join(str(a.get("target", "")) + str(a.get("payload", "")) for a in markers)
    assert DOWN_CODE in target_blob or OFFICIAL_BATCH in target_blob


def test_outfall_down_a_ruling_written_and_locked_today(down_ctx):
    """停用禁采裁决须成文并当日（2026-11-25）锁死，口径为甲路径。"""
    c, h = down_ctx["c"], down_ctx["h"]
    resp = c.get("/api/rulings/down-sampling", headers=h)
    assert resp.status_code == 200, "缺少停用禁采裁决只读口 /api/rulings/down-sampling"
    data = resp.json()
    assert data.get("locked") is True
    assert data.get("date") == RULING_DATE
    assert data.get("path") in ("甲", "a", "A")
    assert "停用禁采" in str(data.get("ruling", ""))
