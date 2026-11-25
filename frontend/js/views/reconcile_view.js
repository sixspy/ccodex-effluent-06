export const reconcileViewTemplate = `
  <div class="grid-2">
    <div class="panel">
      <h3>许可对账（停用口流量已剔除）</h3>
      <div class="actions"><button class="secondary" @click="loadReconcile">刷新全部</button></div>
      <table>
        <thead><tr><th>许可</th><th>对齐</th><th>证明</th><th>封批数</th><th>剔除停用流量</th></tr></thead>
        <tbody>
          <tr v-for="r in reconAllItems" :key="r.permit_code" :class="{'row-down': r.excluded_flow_m3h>0}">
            <td>{{ r.permit_code }}</td>
            <td :class="r.balanced?'pass':'fail'">{{ r.balanced ? "齐" : "不齐" }}</td>
            <td :class="r.proof_ready?'pass':'warn'">{{ r.proof_ready ? "可证" : "未齐" }}</td>
            <td>{{ r.seal_count || 0 }}</td>
            <td><span v-if="r.excluded_flow_m3h>0" class="badge-down">-{{ r.excluded_flow_m3h }} m3/h（{{ r.excluded_sample_count }} 批）</span><span v-else class="muted">0</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel">
      <h3>单许可 / 采样证明</h3>
      <label>许可号</label><input v-model="reconCode"/>
      <div class="actions"><button @click="loadReconcileOne">对账</button></div>

      <div v-if="reconOne && reconOne.excluded_samples && reconOne.excluded_samples.length" class="banner err" style="position:static;margin:.5rem 0">
        已剔除停用排放口流量 {{ reconOne.excluded_flow_m3h }} m3/h（{{ reconOne.excluded_sample_count }} 批），不计入对齐/证明。
      </div>
      <table v-if="reconOne && reconOne.excluded_samples && reconOne.excluded_samples.length">
        <thead><tr><th>剔除批</th><th>口</th><th>流量</th><th>原因</th></tr></thead>
        <tbody>
          <tr v-for="x in reconOne.excluded_samples" :key="x.sample_code" class="row-down">
            <td>{{ x.sample_code }}</td><td>{{ x.outfall_code }}</td><td>{{ x.flow_m3h }}</td>
            <td class="warn">{{ x.excluded_reason }}</td>
          </tr>
        </tbody>
      </table>

      <pre v-if="reconOne" style="white-space:pre-wrap;font-size:0.82rem">{{ JSON.stringify(reconOne, null, 2) }}</pre>
      <label>采样号证明</label><input v-model="proofCode"/>
      <div class="actions"><button class="secondary" @click="loadProof">证明</button></div>
      <pre v-if="proofOne" style="white-space:pre-wrap;font-size:0.82rem">{{ JSON.stringify(proofOne, null, 2) }}</pre>
    </div>
  </div>`;
