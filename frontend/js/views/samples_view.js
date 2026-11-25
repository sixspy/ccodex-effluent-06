export const samplesViewTemplate = `
  <div class="grid-2">
    <div class="panel">
      <h3>采样批次</h3>
      <table>
        <thead><tr><th>编号</th><th>口</th><th>口态</th><th>许可</th><th>流量</th><th>状态</th><th>代</th></tr></thead>
        <tbody>
          <tr v-for="s in samples" :key="s.id" @click="loadSample(s.id)" style="cursor:pointer" :class="{'row-down': s.outfall_status==='停用'}">
            <td>{{ s.sample_code }}</td><td>{{ s.outfall_code }}</td>
            <td>
              <span :class="statusClass(s.outfall_status)">{{ s.outfall_status || '—' }}</span>
              <span v-if="s.outfall_status==='停用'" class="badge-down">禁采</span>
            </td>
            <td>{{ s.permit_ref }}</td>
            <td>{{ s.flow_m3h }}</td><td :class="sampleClass(s.status)">{{ s.status }}</td>
            <td>{{ s.generation }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="sampleDetail" class="panel" style="margin-top:0.8rem;border-style:dashed">
        <h3>批次详情</h3>
        <div class="kv">
          <span>指标</span><span>{{ fmtMetrics(sampleDetail.sample.metrics) }}</span>
          <span>挂起</span><span>{{ sampleDetail.exceed_holds.length }}</span>
          <span>准排</span><span>{{ sampleDetail.discharge_releases.length }}</span>
          <span>封批</span><span>{{ sampleDetail.discharge_seals.length }}</span>
        </div>
      </div>
    </div>
    <div class="panel">
      <h3>入库采样</h3>
      <label>排放口</label>
      <select v-model.number="sampleForm.outfall_id">
        <option v-for="o in outfalls" :key="o.id" :value="o.id">
          {{ o.outfall_code }}（{{ o.status }}）
        </option>
      </select>
      <div v-if="selectedSampleOutfall && selectedSampleOutfall.status==='停用'" class="banner err" style="margin:0.6rem 0">
        {{ selectedSampleOutfall.outfall_code }} 已停用：按 effluent-06 停用禁采裁决（甲）对该口拒建，正式批零增并整笔回退。
      </div>
      <div class="form-row"><div><label>许可号</label><input v-model="sampleForm.permit_ref"/></div></div>
      <div class="form-row">
        <div><label>COD</label><input type="number" v-model.number="sampleForm.cod"/></div>
        <div><label>氨氮</label><input type="number" v-model.number="sampleForm.nh3n"/></div>
      </div>
      <div class="form-row">
        <div><label>总磷</label><input type="number" v-model.number="sampleForm.tp"/></div>
        <div><label>流量 m3/h</label><input type="number" v-model.number="sampleForm.flow_m3h"/></div>
      </div>
      <label>编号（可空自动）</label><input v-model="sampleForm.sample_code"/>
      <div class="actions">
        <button @click="createSample"
          :disabled="selectedSampleOutfall && selectedSampleOutfall.status==='停用'">入库</button>
        <span v-if="selectedSampleOutfall && selectedSampleOutfall.status==='停用'" class="fail" style="margin-left:.6rem">停用口禁采 · 前端已拒建，后端同样硬拒</span>
      </div>
    </div>
  </div>`;
