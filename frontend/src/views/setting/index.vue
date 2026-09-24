<template>
  <section class="page" data-module="setting">
    <header class="page-head">
      <div>
        <h2>系统设置管理</h2>
        <p class="page-desc">系统参数按版本管理：修改先登记为待生效版本，生效后旧取值自动保留为历史，可随时回滚。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记系统参数</button>
        <button class="btn" type="button" @click="exportRows">导出系统设置清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>参数编码</span>
        <input v-model="keyword" placeholder="按参数编码检索" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ formatCell(row, column) }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看</button>
            <button
              v-if="canModify(row)"
              class="link"
              type="button"
              @click="openModify(row)"
            >
              修改参数
            </button>
            <button
              v-if="String(row.status) === '待生效'"
              class="link"
              type="button"
              @click="runAction('生效参数', row)"
            >
              生效参数
            </button>
            <button
              v-if="canRollback(row)"
              class="link"
              type="button"
              @click="runAction('回滚参数', row)"
            >
              回滚参数
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无系统设置数据，可先登记系统参数</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条系统参数记录（含历史版本）</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 修改参数：只在待生效版本确认前生效前录入新取值，提交后生成一条待生效新版本 -->
    <div v-if="modifyOpen" class="modal-mask" @click.self="closeModify">
      <div class="modal">
        <h3>修改参数 · {{ String(modifyForm.参数编码) }}（当前 v{{ String(modifyForm.版本) }}）</h3>
        <p class="modal-tip">
          当前已生效取值：{{ String(modifyForm.当前值) }}；修改后生成待生效新版本，确认无误再执行生效参数。
        </p>
        <label class="modal-field">
          <span>新参数值 <em>*</em></span>
          <input v-model="modifyForm.参数值" placeholder="请输入新的参数值" />
        </label>
        <label class="modal-field">
          <span>生效范围</span>
          <input v-model="modifyForm.生效范围" placeholder="留空则沿用当前生效范围" />
        </label>
        <label class="modal-field">
          <span>修改人</span>
          <input v-model="modifyForm.修改人" placeholder="留空则沿用当前修改人" />
        </label>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeModify">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitModify">
            提交修改
          </button>
        </div>
      </div>
    </div>

    <!-- 详情：列表与详情读取同一份版本记录，并展示该参数编码下的全部历史取值 -->
    <div v-if="detailRow" class="modal-mask" @click.self="closeDetail">
      <div class="modal">
        <h3>参数版本详情 · {{ String(detailRow.参数编码) }} v{{ String(detailRow.版本) }}</h3>
        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ formatCell(detailRow, field) }}</dd>
          </template>
        </dl>
        <h4 class="history-title">历史取值（同参数编码全部版本）</h4>
        <table class="data-table history-table">
          <thead>
            <tr>
              <th v-for="column in historyColumns" :key="column">{{ column }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in historyRows" :key="String(item.id)">
              <td v-for="column in historyColumns" :key="column">{{ formatCell(item, column) }}</td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/setting'
const columns = ["参数编码", "版本", "状态", "参数名称", "参数值", "参数类型", "生效范围", "修改人"]
const historyColumns = ["版本", "状态", "参数值", "生效范围", "修改人"]
const detailFields = ["参数编码", "版本", "状态", "参数名称", "参数值", "参数类型", "生效范围", "修改人"]
const statuses = ["已生效", "待生效", "已回滚"]

const rows = ref<Row[]>([])
const allRows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const submitting = ref(false)

const stats = computed(() => [
  { label: "已生效参数版本", value: allRows.value.filter(row => String(row.status) === '已生效').length },
  { label: "待生效参数", value: allRows.value.filter(row => String(row.status) === '待生效').length },
  { label: "历史版本", value: allRows.value.filter(row => String(row.status) === '已回滚').length },
])

const modifyOpen = ref(false)
const modifyForm = ref<{ id: number; 参数编码: string; 版本: number | string; 当前值: string; 参数值: string; 生效范围: string; 修改人: string }>({
  id: 0,
  参数编码: '',
  版本: '',
  当前值: '',
  参数值: '',
  生效范围: '',
  修改人: '',
})

const detailRow = ref<Row | null>(null)
const historyRows = ref<Row[]>([])

function formatCell(row: Row, column: string): string {
  if (column === '状态') return String(row.status ?? '—')
  const value = row[column]
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

// 待生效版本尚未生效，已生效版本才能发起下一次修改；历史版本不可改
function canModify(row: Row): boolean {
  return String(row.status) === '已生效'
}

// 待生效版本可作废；已生效版本在按钮层面开放，是否存在可恢复历史由后端判定并提示
function canRollback(row: Row): boolean {
  return String(row.status) === '待生效' || String(row.status) === '已生效'
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '系统参数登记入口尚未接入审批流'
}

function openModify(row: Row) {
  errorMessage.value = ''
  modifyForm.value = {
    id: Number(row.id),
    参数编码: String(row.参数编码 ?? ''),
    版本: String(row.版本 ?? ''),
    当前值: String(row.参数值 ?? ''),
    参数值: '',
    生效范围: '',
    修改人: '',
  }
  modifyOpen.value = true
}

function closeModify() {
  modifyOpen.value = false
}

async function submitModify() {
  errorMessage.value = ''
  const value = modifyForm.value.参数值.trim()
  if (!value) {
    errorMessage.value = '请填写新的参数值'
    return
  }
  submitting.value = true
  try {
    const response = await request(`${ENDPOINT}/${modifyForm.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        action: '修改参数',
        参数值: value,
        生效范围: modifyForm.value.生效范围.trim(),
        修改人: modifyForm.value.修改人.trim(),
      }),
    })
    const payload = await response.json().catch(() => null) as { ok?: boolean; message?: string } | null
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '修改参数未生效，请稍后重试')
    }
    noticeMessage.value = payload.message || '修改已登记为待生效版本'
    closeModify()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '修改参数失败'
  } finally {
    submitting.value = false
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  detailRow.value = row
  historyRows.value = []
  try {
    const response = await request(`${ENDPOINT}/${row.id}/history`)
    if (!response.ok) {
      throw new Error('历史版本读取失败')
    }
    const payload = await response.json() as { items?: Row[] }
    historyRows.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '历史版本读取失败'
  }
}

function closeDetail() {
  detailRow.value = null
  historyRows.value = []
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null) as { ok?: boolean; message?: string } | null
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '系统设置动作未生效，请稍后重试')
    }
    noticeMessage.value = payload.message || '操作已完成'
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '系统设置操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value.trim()) {
    params.set('keyword', keyword.value.trim())
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  // 统计卡片需要全量口径：有筛选条件时额外拉一次全量，保证数字不被筛选条件带偏
  try {
    const [filtered, all] = await Promise.all([
      request(`${ENDPOINT}?${params.toString()}`),
      params.toString() ? request(ENDPOINT) : Promise.resolve(null),
    ])
    if (!filtered.ok) {
      throw new Error('系统参数列表读取失败')
    }
    const payload = await filtered.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (all) {
      const allPayload = await all.json()
      allRows.value = allPayload.items ?? []
    } else {
      allRows.value = rows.value
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '系统参数列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.notice-text { color: #067647; }
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal {
  background: #fff;
  border-radius: 8px;
  padding: 18px 20px;
  width: 560px;
  max-width: calc(100vw - 32px);
  max-height: 82vh;
  overflow: auto;
}
.modal h3 { margin: 0 0 8px; font-size: 15px; }
.modal-tip { margin: 0 0 12px; color: var(--muted); font-size: 12px; }
.modal-field { display: block; margin-bottom: 10px; }
.modal-field span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.modal-field em { color: #b42318; font-style: normal; }
.modal-field input { width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.detail-grid { display: grid; grid-template-columns: 90px 1fr 90px 1fr; gap: 6px 10px; margin: 0 0 12px; font-size: 13px; }
.detail-grid dt { color: var(--muted); }
.detail-grid dd { margin: 0; }
.history-title { font-size: 13px; margin: 4px 0 8px; }
.history-table th, .history-table td { font-size: 12px; padding: 6px 8px; }
</style>
