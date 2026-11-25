export const outfallsViewTemplate = `
  <div class="panel ruling-bar">
    <strong>effluent-06 停用禁采裁决（2026-11-25 当日锁死 · 甲路径）</strong>
    <span>排放口一旦停用，采样写口正式区零增并整笔回退；对账剔除该口流量，总览计流清零。强写记「停用禁采偏航」。</span>
  </div>
  <div class="grid-2">
    <div class="panel">
      <h3>排放口限值与停用禁采态</h3>
      <table>
        <thead><tr><th>编码</th><th>厂</th><th>河段</th><th>COD</th><th>氨氮</th><th>总磷</th><th>状态</th><th>口径流量 m3/h</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="o in outfalls" :key="o.id" :class="{'row-down': o.status==='停用'}">
            <td>{{ o.outfall_code }}</td><td>{{ o.plant_code }}</td><td>{{ o.river_reach }}</td>
            <td>{{ o.cod_limit }}</td><td>{{ o.nh3n_limit }}</td><td>{{ o.tp_limit }}</td>
            <td>
              <span :class="statusClass(o.status)">{{ o.status }}</span>
              <span v-if="o.status==='停用'" class="badge-down">停用禁采</span>
            </td>
            <td>
              <span :class="{'flow-zero': o.status==='停用'}">{{ o.sample_flow_m3h != null ? o.sample_flow_m3h : '—' }}</span>
              <span v-if="o.status==='停用'" class="muted">（清零，原 {{ o.raw_sample_flow_m3h }}）</span>
            </td>
            <td class="actions-cell">
              <button v-if="o.status!=='停用'" class="warn tiny" @click="setOutfallStatus(o,'停用')">停用</button>
              <button v-else class="secondary tiny" @click="setOutfallStatus(o,'开放')">启用</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="muted">停用标签亮即禁采：采样页对该口拒建，处理厂页下属口状态与本页同源一致。</p>
    </div>
    <div class="panel">
      <h3>新建排放口</h3>
      <div class="form-row"><div><label>编码</label><input v-model="outfallForm.outfall_code"/></div>
      <div><label>处理厂 ID</label><input type="number" v-model.number="outfallForm.plant_id"/></div></div>
      <label>河段</label><input v-model="outfallForm.river_reach"/>
      <div class="form-row">
        <div><label>COD 限</label><input type="number" v-model.number="outfallForm.cod_limit"/></div>
        <div><label>氨氮限</label><input type="number" v-model.number="outfallForm.nh3n_limit"/></div>
      </div>
      <label>总磷限</label><input type="number" v-model.number="outfallForm.tp_limit"/>
      <div class="actions"><button @click="createOutfall">登记</button></div>
    </div>
  </div>`;
