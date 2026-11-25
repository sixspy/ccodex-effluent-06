# -*- coding: utf-8 -*-
"""effluent-06 并发闸：race_outfall_create。

两路会话同时对同一个排放口抢建批：
- 确定性一幕：胜方持已提交的 outfall 口锁，后到会话必须 409、零行、留争用痕；
- 真并发一幕：Barrier 齐放两个 POST，同编号正式批恰好一行、仅一路 2xx。

修复前确定性一幕见红（争用痕被回滚吞掉 / 同 holder 可重入双建）。
"""
from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import app
from db import init_db


def login(user: str = "admin", pw: str = "admin123"):
    c = TestClient(app)
    tok = c.post("/api/login", json={"username": user, "password": pw}).json()["token"]
    return c, {"Authorization": "Bearer " + tok}


@pytest.fixture()
def race_db(tmp_path, monkeypatch):
    import db

    db_file = tmp_path / "race_outfall_create.db"
    monkeypatch.setattr(db, "DB_PATH", db_file)
    init_db()
    c, h = login()
    of = next(o for o in c.get("/api/outfalls", headers=h).json()["items"]
              if o["outfall_code"] == "OF-E1-B")
    return {"db": db_file, "c": c, "h": h, "of": of}


def body(of_id: int, code: str) -> dict:
    return {
        "outfall_id": of_id,
        "permit_ref": "DP-2026-E01",
        "sample_code": code,
        "flow_m3h": 88,
        "metrics": {"cod": 9.0, "nh3n": 0.8, "tp": 0.08},
    }


def race_outfall_create(of_id: int, code: str = "SM-RACE-NAMED"):
    """供并发双请求复用：两路独立会话齐放同口建批，返回状态码列表。"""
    barrier = threading.Barrier(2)

    def one(_):
        c, h = login()
        barrier.wait()
        return c.post("/api/samples", headers=h, json=body(of_id, code)).status_code

    with ThreadPoolExecutor(max_workers=2) as ex:
        return list(ex.map(one, [0, 1]))


def test_race_outfall_create(race_db):
    """同名主闸：后到会话抢口锁失败 -> 409 + durable 争用痕 + 败方零行。"""
    c, h, of = race_db["c"], race_db["h"], race_db["of"]
    db_file = race_db["db"]
    key = f"outfall:{of['id']}"
    assert c.post(f"/api/locks/acquire?lock_key={key}", headers=h).status_code == 200

    c2, h2 = login("writer", "writer123")
    r = c2.post("/api/samples", headers=h2, json=body(of["id"], "SM-RACE-MAIN"))
    assert r.status_code == 409, r.text

    con = sqlite3.connect(db_file)
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM sample_batches WHERE sample_code='SM-RACE-MAIN'"
        ).fetchone()[0]
    finally:
        con.close()
    assert n == 0

    logs = c.get("/api/locks", headers=h).json()["contention"]
    assert any(x.get("lock_key") == key and x.get("action") == "争用失败" for x in logs), logs


def test_race_outfall_create_parallel_helper_single_row(race_db):
    """真并发双请求：同口同编号只允许一行正式批，且仅一路 2xx。"""
    of, db_file = race_db["of"], race_db["db"]
    # 种子夹具预置 E1-B 停用；本用例验证开放口的建成仲裁，显式恢复开放。
    race_db["c"].post(
        f"/api/outfalls/{of['id']}/status?status=开放", headers=race_db["h"]
    )
    statuses = race_outfall_create(of["id"], "SM-RACE-HELPER")
    con = sqlite3.connect(db_file)
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM sample_batches WHERE sample_code='SM-RACE-HELPER'"
        ).fetchone()[0]
    finally:
        con.close()
    assert n == 1, statuses
    assert statuses.count(200) == 1, statuses


def test_race_outfall_create_on_down_outfall_both_rejected_zero_rows(race_db):
    """停用 OF-E1-B 后两路会话同口并发抢建：正式批零行，状态只能是 400/409。

    时序无关：交叠则后到吃口锁 409，串行则各吃停用裁决 400；无论哪种，
    停用口都不得出正式批，败方（事实上两路）零行。
    """
    c, h, of = race_db["c"], race_db["h"], race_db["of"]
    db_file = race_db["db"]
    assert c.post(f"/api/outfalls/{of['id']}/status?status=停用", headers=h).status_code == 200

    barrier = threading.Barrier(2)

    def fire(_):
        cc, hh = login("writer", "writer123")
        barrier.wait()
        r = cc.post("/api/samples", headers=hh, json=body(of["id"], "SM-RACE-DOWN-PAR"))
        return r.status_code

    with ThreadPoolExecutor(max_workers=2) as ex:
        statuses = list(ex.map(fire, [0, 1]))

    assert all(code in (400, 409) for code in statuses), statuses
    con = sqlite3.connect(db_file)
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM sample_batches WHERE sample_code='SM-RACE-DOWN-PAR'"
        ).fetchone()[0]
    finally:
        con.close()
    assert n == 0, "停用口双会话抢建不得有任何正式批落库"
