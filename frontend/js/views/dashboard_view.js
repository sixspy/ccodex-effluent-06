export const dashboardViewTemplate = `
  <section class="hero-strip">
    <h2>污水排放批总览</h2>
    <p>采样入库 → 超标挂起 → 准排裁定 → 封批升代 → 许可对账</p>
  </section>
  <div class="stats">
    <div class="stat"><div class="n">{{ dash.plants || 0 }}</div><div class="l">处理厂</div></div>
    <div class="stat"><div class="n">{{ dash.outfalls || 0 }}</div><div class="l">排放口</div></div>
    <div class="stat"><div class="n">{{ dash.samples || 0 }}</div><div class="l">采样批次</div></div>
    <div class="stat"><div class="n">{{ dash.open_exceeds || 0 }}</div><div class="l">开放超标</div></div>
    <div class="stat"><div class="n">{{ dash.discharge_releases || 0 }}</div><div class="l">已准排</div></div>
    <div class="stat"><div class="n">{{ dash.discharge_seals || 0 }}</div><div class="l">已封批</div></div>
    <div class="stat"><div class="n">{{ dash.permits || 0 }}</div><div class="l">许可册</div></div>
    <div class="stat"><div class="n">{{ dash.side_pending || 0 }}</div><div class="l">旁路挂起</div></div>
  </div>

  <div class="grid-2">
    <div class="panel">
      <h3>effluent-06 停用口流量同态核销</h3>
      <div class="stats compact-stats">
        <div class="stat"><div class="n flow-zero">{{ dash.down_outfall_flow_m3h != null ? dash.down_outfall_flow_m3h : 0 }}</div><div class="l">停用口计流 m3/h（清零）</div></div>
        <div class="stat"><div class="n warn">{{ dash.excluded_down_flow_m3h || 0 }}</div><div class="l">对账已剔除停用流量</div></div>
        <div class="stat"><div class="n">{{ dash.down_outfall_count || 0 }}</div><div class="l">停用排放口</div></div>
        <div class="stat"><div class="n pass">{{ dash.flow_total_m3h || 0 }}</div><div class="l">在统流量 m3/h</div></div>
      </div>
      <p class="muted">停用口在总览对外计流一律为 0；其历史正式批流量仅作“已剔除”透明留痕，与排放口页/采样页/处理厂页/对账页同态。</p>
    </div>
    <div class="panel">
      <h3>各排放口计流（停用口清零）</h3>
      <table>
        <thead><tr><th>编码</th><th>状态</th><th>原始累计</th><th>口径计流</th></tr></thead>
        <tbody>
          <tr v-for="f in (dash.outfall_flows || [])" :key="f.outfall_code" :class="{'row-down': f.zeroed}">
            <td>{{ f.outfall_code }}</td>
            <td><span :class="statusClass(f.status)">{{ f.status }}</span></td>
            <td class="muted">{{ f.raw_flow_m3h }}</td>
            <td :class="f.zeroed ? 'flow-zero' : 'pass'">{{ f.flow_m3h }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

    <div class="panel">
      <h3>产品骨架</h3>
      <p class="muted">{{ (dash.meta && dash.meta.skeleton) || "—" }}</p>
    </div>`;
