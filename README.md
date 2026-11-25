# 污水排放批（effluent）

数据工程母仓：处理厂采样入库 → 超标旁路挂起 → 准排放裁定 → 封批升代 → 排放许可对账。

## 骨架一句话

采样批次入库后裁定超标才准排放封批，驳回进旁路挂起，指标血缘与排放许可对账。

## 一键起环境

```bash
docker compose up -d --build
```

浏览器访问 http://localhost:11600

- 管理账号：`admin` / `admin123`
- 读写账号：`writer` / `writer123`
- 只读账号：`viewer` / `viewer123`

## 本地开发

```powershell
cd projects/14-effluent
$env:PYTHONPATH="backend"
python -m uvicorn app:app --app-dir backend --reload --port 8000
```

## 自测

```powershell
$env:PYTHONPATH="backend"
python -m pytest
python scripts/count_loc.py
```

## effluent-06 停用排放口禁采样（2026-11-25 当日锁死）

裁决取**甲路径**：排放口（如 `OF-E1-B`）一旦 `停用`，`POST /api/samples` 对该口
**正式区零增并整笔回退**，不得出正式批（如 `SM-F03`）；强写另笔记
`停用禁采偏航` 审计痕。停用/启用与采样抢同一把会话口锁 `outfall:{id}`，两路会话
同口抢建后到者 409、零行并留 durable `争用失败` 痕。对账剔除停用口流量，总览停用口
计流清零；排放口/采样/处理厂/对账/总览五页同态。详见
[`docs/effluent-06-停用禁采裁决.md`](docs/effluent-06-停用禁采裁决.md)。

闸口测试：`pytest tests/outfall_down_a.py tests/outfall_down_b.py tests/outfall_down_c.py tests/race_outfall_create.py`
（先见三红，后分服务救绿）。

