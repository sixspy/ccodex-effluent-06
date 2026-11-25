"""排放许可与采样对账证明。"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
from validators import validate_permit_match

router = APIRouter(tags=["reconcile"])


@router.get("/api/reconcile")
def reconcile_all(authorization: AuthHeader = None):
    require_user(authorization)
    from db import connect

    with connect() as conn:
        rows = conn.execute(
            "SELECT permit_code FROM discharge_permits ORDER BY permit_code"
        ).fetchall()
        return {"items": [_reconcile_permit(conn, r["permit_code"]) for r in rows]}


@router.get("/api/reconcile/{permit_code}")
def reconcile_one(permit_code: str, authorization: AuthHeader = None):
    require_user(authorization)
    from db import connect

    with connect() as conn:
        if not conn.execute(
            "SELECT id FROM discharge_permits WHERE permit_code=?", (permit_code,)
        ).fetchone():
            raise HTTPException(404, "许可不存在")
        return _reconcile_permit(conn, permit_code)


def _reconcile_permit(conn, permit_code: str) -> dict:
    permit = conn.execute(
        "SELECT * FROM discharge_permits WHERE permit_code=?", (permit_code,)
    ).fetchone()
    # effluent-06：关联 outfalls.status，停用口流量必须从对账口径剔除。
    samples = conn.execute(
        """SELECT s.sample_code, s.flow_m3h, s.metrics, s.status, s.generation,
                  o.outfall_code, o.status AS outfall_status
           FROM sample_batches s
           JOIN outfalls o ON o.id=s.outfall_id
           WHERE s.permit_ref=? AND s.status NOT IN ('作废')
           ORDER BY s.id""",
        (permit_code,),
    ).fetchall()
    if not samples:
        return {
            "permit_code": permit_code,
            "balanced": False,
            "reason": "无采样批次",
            "samples": [],
            "excluded_samples": [],
            "excluded_flow_m3h": 0.0,
        }
    caps = {
        "cod": permit["cod_cap"],
        "nh3n": permit["nh3n_cap"],
        "tp": permit["tp_cap"],
    }
    details = []
    excluded = []
    all_ok = True
    counted_flow = 0.0
    excluded_flow = 0.0
    for s in samples:
        metrics = json.loads(s["metrics"] or "{}")
        flow = float(s["flow_m3h"])
        base = {
            "sample_code": s["sample_code"],
            "status": s["status"],
            "generation": s["generation"],
            "metrics": metrics,
            "flow_m3h": s["flow_m3h"],
            "outfall_code": s["outfall_code"],
            "outfall_status": s["outfall_status"],
        }
        if s["outfall_status"] == "停用":
            # 停用口：不参与对齐/证明，流量进剔除台账，绝不累计。
            excluded_flow += flow
            excluded.append(
                {
                    **base,
                    "matched": None,
                    "excluded_reason": "停用排放口流量剔除（effluent-06 停用禁采）",
                }
            )
            continue
        ok = validate_permit_match(
            caps, metrics, flow, float(permit["quota_m3d"])
        )
        if not ok:
            all_ok = False
        counted_flow += flow
        details.append({**base, "matched": ok})
    seal_rows = conn.execute(
        """SELECT d.seal_ref, d.sample_generation, s.sample_code
           FROM discharge_seals d JOIN sample_batches s ON s.id=d.sample_id
           JOIN outfalls o ON o.id=s.outfall_id
           WHERE s.permit_ref=? AND o.status!='停用'""",
        (permit_code,),
    ).fetchall()
    return {
        "permit_code": permit_code,
        "quota_m3d": permit["quota_m3d"],
        "caps": caps,
        "balanced": all_ok,
        "proof_ready": all_ok and len(seal_rows) >= 1,
        "seal_count": len(seal_rows),
        "samples": details,
        # effluent-06 停用口剔除同态字段
        "excluded_samples": excluded,
        "excluded_sample_count": len(excluded),
        "excluded_flow_m3h": excluded_flow,
        "counted_flow_m3h": counted_flow,
        "total_flow_m3h": counted_flow,
        "seals": [dict(x) for x in seal_rows],
    }


@router.get("/api/proof/sample/{sample_code}")
def proof_sample(sample_code: str, authorization: AuthHeader = None):
    require_user(authorization)
    from db import connect

    with connect() as conn:
        sample = conn.execute(
            "SELECT * FROM sample_batches WHERE sample_code=?", (sample_code,)
        ).fetchone()
        if not sample:
            raise HTTPException(404, "采样不存在")
        holds = conn.execute(
            "SELECT * FROM exceed_holds WHERE sample_id=?", (sample["id"],)
        ).fetchall()
        releases = conn.execute(
            "SELECT * FROM discharge_releases WHERE sample_id=?", (sample["id"],)
        ).fetchall()
        seals = conn.execute(
            "SELECT * FROM discharge_seals WHERE sample_id=?", (sample["id"],)
        ).fetchall()
        open_holds = [h for h in holds if h["status"] == "开放"]
        closed = [h for h in holds if h["status"] == "已关闭"]
        return {
            "sample_code": sample_code,
            "status": sample["status"],
            "generation": sample["generation"],
            "released": any(r["status"] == "已准排" for r in releases),
            "sealed": any(s["status"] == "已封批" for s in seals),
            "exceed_closed": len(open_holds) == 0 and (len(closed) > 0 or sample["status"] != "旁路挂起"),
            "holds": [dict(h) for h in holds],
            "releases": [dict(r) for r in releases],
            "seals": [dict(s) for s in seals],
        }
