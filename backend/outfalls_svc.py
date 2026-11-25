"""排放口限值与开放态。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit
from locks import acquire_session_lock, release_session_lock
from models import OutfallIn

router = APIRouter(tags=["outfalls"])

DOWN_STATUS = "停用"

# effluent-06 停用禁采裁决（2026-11-25 当日锁死，口径取甲路径）。
DOWN_SAMPLING_RULING = {
    "key": "effluent-06:down-sampling",
    "slot": "排污己第6槽",
    "date": "2026-11-25",
    "locked": True,
    "lock_note": "裁决当日锁死，停用态与采样落库不得混用，旁门禁止",
    "path": "甲",
    "path_options": ["甲", "乙"],
    "ruling": (
        "甲路径：排放口一旦停用，采样写口正式区零增并整笔回退；"
        "停用口不得出正式采样批。强写另笔记录“停用禁采偏航”并拒写。"
    ),
    "marker": "停用禁采偏航",
    "official_area": "sample_batches",
}


def _flow_map(conn) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for r in conn.execute(
        """SELECT o.id, o.status,
                  COALESCE(SUM(CASE WHEN s.status!='作废' THEN s.flow_m3h END),0) raw_flow,
                  COUNT(s.id) sample_count
           FROM outfalls o LEFT JOIN sample_batches s ON s.outfall_id=o.id
           GROUP BY o.id"""
    ).fetchall():
        raw = float(r["raw_flow"] or 0.0)
        is_down = r["status"] == DOWN_STATUS
        out[r["id"]] = {
            "sample_count": r["sample_count"],
            "raw_sample_flow_m3h": raw,
            # 停用口对外计流清零。
            "sample_flow_m3h": 0.0 if is_down else raw,
            "flow_m3h": 0.0 if is_down else raw,
            "sampling_allowed": r["status"] == "开放",
        }
    return out


@router.get("/api/rulings/down-sampling")
def get_down_sampling_ruling(authorization: AuthHeader = None):
    require_user(authorization)
    return dict(DOWN_SAMPLING_RULING)


@router.get("/api/outfalls")
def list_outfalls(authorization: AuthHeader = None, plant_id: int | None = None):
    require_user(authorization)
    with connect() as conn:
        flows = _flow_map(conn)
        if plant_id:
            rows = conn.execute(
                """SELECT o.*, p.plant_code, p.name plant_name FROM outfalls o
                   JOIN plants p ON p.id=o.plant_id WHERE o.plant_id=? ORDER BY o.id""",
                (plant_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT o.*, p.plant_code, p.name plant_name FROM outfalls o
                   JOIN plants p ON p.id=o.plant_id ORDER BY o.id"""
            ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d.update(flows.get(r["id"], {}))
            items.append(d)
        return {"items": items}


@router.get("/api/outfalls/{outfall_id}")
def get_outfall(outfall_id: int, authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        row = conn.execute(
            """SELECT o.*, p.plant_code, p.design_cap_m3d FROM outfalls o
               JOIN plants p ON p.id=o.plant_id WHERE o.id=?""",
            (outfall_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "排放口不存在")
        flows = _flow_map(conn)
        data = dict(row)
        data.update(flows.get(outfall_id, {}))
        recent = conn.execute(
            """SELECT sample_code, status, flow_m3h, created_at FROM sample_batches
               WHERE outfall_id=? ORDER BY id DESC LIMIT 10""",
            (outfall_id,),
        ).fetchall()
        return {"outfall": data, "recent_samples": [dict(s) for s in recent]}


@router.post("/api/outfalls")
def create_outfall(body: OutfallIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        plant = conn.execute(
            "SELECT * FROM plants WHERE id=?", (body.plant_id,)
        ).fetchone()
        if not plant:
            raise HTTPException(404, "处理厂不存在")
        if conn.execute(
            "SELECT id FROM outfalls WHERE outfall_code=?", (body.outfall_code,)
        ).fetchone():
            raise HTTPException(400, "排放口编码已存在")
        cur = conn.execute(
            """INSERT INTO outfalls(outfall_code,plant_id,river_reach,cod_limit,nh3n_limit,
               tp_limit,status,created_at) VALUES (?,?,?,?,?,?,?,?)""",
            (
                body.outfall_code,
                body.plant_id,
                body.river_reach,
                body.cod_limit,
                body.nh3n_limit,
                body.tp_limit,
                body.status,
                now_iso(),
            ),
        )
        oid = cur.lastrowid
        write_audit(conn, user, "outfall_create", body.outfall_code, body.model_dump())
        conn.commit()
        return {"id": oid, **body.model_dump()}


@router.post("/api/outfalls/{outfall_id}/status")
def set_outfall_status(outfall_id: int, status: str, authorization: AuthHeader = None):
    user = require_writer(authorization)
    if status not in ("开放", "停用", "检修"):
        raise HTTPException(400, "非法状态")
    lock_key = f"outfall:{outfall_id}"
    # 停用/启用与采样建批抢同一把口锁，闭合“读到开放后被停用”的交叉窗口。
    token = acquire_session_lock(lock_key, user)
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM outfalls WHERE id=?", (outfall_id,)
            ).fetchone()
            if not row:
                raise HTTPException(404, "排放口不存在")
            conn.execute("UPDATE outfalls SET status=? WHERE id=?", (status, outfall_id))
            write_audit(
                conn, user, "outfall_status", row["outfall_code"], {"status": status}
            )
            if status == DOWN_STATUS:
                write_audit(
                    conn,
                    user,
                    "停用禁采裁决生效",
                    row["outfall_code"],
                    {
                        "status": status,
                        "ruling": "effluent-06",
                        "path": "甲",
                        "date_lock": "2026-11-25",
                        "effect": "采样写口对该口拒写，对账与总览剔除/清零该口流量",
                    },
                )
            conn.commit()
            return {"id": outfall_id, "status": status}
    finally:
        release_session_lock(lock_key, token)
