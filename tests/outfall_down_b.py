# -*- coding: utf-8 -*-
"""effluent-06 红测乙：对账必须剔除停用排放口流量。

OF-E1-B 停用后，其已落正式批 SM-OF-E1-B-001（flow_m3h=1200，挂在
DP-2026-E01）不得再进入对账采样明细/流量累计；应被识别为剔除项。

修复前应见红：reconcile_svc._reconcile_permit 只按 permit_ref 取批，
不关联 outfalls.status，停用口流量仍被计入。
"""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import app
from db import init_db

DOWN_CODE = "OF-E1-B"
DOWN_SAMPLE = "SM-OF-E1-B-001"
PERMIT = "DP-2026-E01"
DOWN_FLOW = 1200.0


def _auth(c: TestClient) -> dict:
    tok = c.post(
        "/api/login", json={"username": "admin", "password": "admin123"}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


@pytest.fixture()
def down_ctx(tmp_path, monkeypatch):
    import db

    db_file = tmp_path / "outfall_down_b.db"
    monkeypatch.setattr(db, "DB_PATH", db_file)
    init_db()
    c = TestClient(app)
    h = _auth(c)
    of = next(o for o in c.get("/api/outfalls", headers=h).json()["items"]
              if o["outfall_code"] == DOWN_CODE)
    assert c.post(f"/api/outfalls/{of['id']}/status?status=停用", headers=h).status_code == 200

    def db_rows(sql, args=()):
        con = sqlite3.connect(db_file)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        finally:
            con.close()

    yield {"c": c, "h": h, "of": of, "rows": db_rows}


def test_outfall_down_b_reconcile_drops_down_outfall_sample(down_ctx):
    """乙断言：对账明细不再含停用口批次 SM-OF-E1-B-001。"""
    c, h = down_ctx["c"], down_ctx["h"]
    data = c.get(f"/api/reconcile/{PERMIT}", headers=h).json()
    codes = [s["sample_code"] for s in data["samples"]]
    assert DOWN_SAMPLE not in codes, f"停用口流量仍计入对账：{codes}"


def test_outfall_down_b_reconcile_flow_excludes_down_flow(down_ctx):
    """乙断言：对账累计流量剔除停用口 1200，且给出剔除台账。"""
    c, h = down_ctx["c"], down_ctx["h"]
    data = c.get(f"/api/reconcile/{PERMIT}", headers=h).json()

    counted_flow = sum(float(s["flow_m3h"]) for s in data["samples"])
    # E01 现存 E1-A 两批 2800/2900；停用的 E1-B 1200 绝不能混进累计。
    assert all(abs(float(s["flow_m3h"]) - DOWN_FLOW) > 1e-6 for s in data["samples"])
    assert abs(counted_flow - (2800.0 + 2900.0)) < 1e-6

    excluded = data.get("excluded_samples", [])
    assert any(x.get("sample_code") == DOWN_SAMPLE for x in excluded), \
        "应对停用口批次给出 excluded_samples 剔除台账"
    assert float(data.get("excluded_flow_m3h", 0)) == DOWN_FLOW


def test_outfall_down_b_reconcile_all_consistent(down_ctx):
    """全量对账口与单许可口同态：E01 均不得再计停用口批次。"""
    c, h = down_ctx["c"], down_ctx["h"]
    items = c.get("/api/reconcile", headers=h).json()["items"]
    e01 = next(p for p in items if p["permit_code"] == PERMIT)
    codes = [s["sample_code"] for s in e01["samples"]]
    assert DOWN_SAMPLE not in codes
