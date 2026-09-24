<template>
  <section class="page" data-module="setting">
    <header class="page-head">
      <div>
        <h2>系统设置管理</h2>
        <p class="page-desc">维护系统参数，围绕参数编码、参数名称、参数值、参数类型做登记、筛选与状态流转。同一参数编码的每次取值都留版本，历史取值不覆盖。</p>
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
        <input v-model="filters.keyword" placeholder="按参数编码检索" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="filters.status">
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
          <th>状态</th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td><span class="status-tag" :class="String(row.status)">{{ row.status ?? '—' }}</span></td>
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="openAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无系统设置数据，可先登记系统参数</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条系统设置记录（含历史版本）</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>

    <!-- 详情弹窗：直接取 GET /{id}，与列表行是同一条记录，刷新后取值不变 -->
    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card">
        <div class="modal-head">
          <h3>参数详情（记录 #{{ detail.id }}）</h3>
          <button class="modal-close" type="button" @click="closeDetail">×</button>
        </div>
        <ul class="detail-list">
          <li v-for="field in detailFields" :key="field">
            <span class="detail-key">{{ field }}</span>
            <span>{{ detail[field] ?? '—' }}</span>
          </li>
          <li>
            <span class="detail-key">状态</span>
            <span class="status-tag" :class="String(detail.status)">{{ detail.status ?? '—' }}</span>
          </li>
        </ul>
        <h4 style="margin: 14px 0 6px; font-size: 13px;">同参数编码的全部版本</h4>
        <table class="data-table">
          <thead>
            <tr><th>记录</th><th>参数值</th><th>生效范围</th><th>状态</th></tr>
          </thead>
          <tbody>
            <tr v-for="version in detailVersions" :key="String(version.id)" :class="{ 'is-current': version.id === detail.id }">
              <td>#{{ version.id }}</td>
              <td>{{ version['参数值'] ?? '—' }}</td>
              <td>{{ version['生效范围'] ?? '—' }}</td>
              <td><span class="status-tag" :class="String(version.status)">{{ version.status ?? '—' }}</span></td>
            </tr>
            <tr v-if="!detailVersions.length">
              <td colspan="4" class="empty-state">暂无版本数据</td>
            </tr>
          </tbody>
        </table>
        <div class="modal-foot">
          <button class="btn" type="button" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>

    <!-- 修改参数弹窗：以当前已生效取值为底，提交后生成待生效新版本 -->
    <div v-if="editing" class="modal-mask" @click.self="closeEditor">
      <div class="modal-card">
        <div class="modal-head">
          <h3>{{ editing.action }}</h3>
          <button class="modal-close" type="button" @click="closeEditor">×</button>
        </div>
        <form @submit.prevent="submitEditor">
          <div class="form-item">
            <label>参数编码（不可改）</label>
            <input :value="editing.form['参数编码']" readonly />
          </div>
          <div v-for="field in editFields" :key="field" class="form-item">
            <label>{{ field }}<span v-if="field === '参数值'" class="error-text"> *</span></label>
            <input v-model="editing.form[field]" :placeholder="`请输入${field}`" />
          </div>
          <p class="page-desc">提交后生成一条「待生效」新版本，当前已生效取值保持不变；在列表执行「生效参数」后切换。</p>
          <div class="modal-foot">
            <button class="btn" type="button" @click="closeEditor">取消</button>
            <button class="btn primary" type="submit">提交</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 登记弹窗 -->
    <div v-if="creating" class="modal-mask" @click.self="closeCreate">
      <div class="modal-card">
        <div class="modal-head">
          <h3>登记系统参数</h3>
          <button class="modal-close" type="button" @click="closeCreate">×</button>
        </div>
        <form @submit.prevent="submitCreate">
          <div v-for="field in createFields" :key="field" class="form-item">
            <label>{{ field }}<span v-if="field === '参数编码' || field === '参数名称' || field === '参数值'" class="error-text"> *</span></label>
            <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
          </div>
          <div class="modal-foot">
            <button class="btn" type="button" @click="closeCreate">取消</button>
            <button class="btn primary" type="submit">登记</button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/setting'
const columns = ["参数编码", "参数名称", "参数值", "参数类型", "生效范围", "修改人"]
const detailFields = ["参数编码", "参数名称", "参数值", "参数类型", "生效范围", "修改人"]
const editFields = ["参数名称", "参数值", "参数类型", "生效范围", "修改人"]
const createFields = ["参数编码", "参数名称", "参数值", "参数类型", "生效范围", "修改人"]
const actions = ["修改参数", "回滚参数", "生效参数"]
const statuses = ["已生效", "待生效", "已回滚", "已失效"]
const stats = [{"label": "生效参数", "value": 0}, {"label": "待生效参数", "value": 0}, {"label": "历史版本数", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const filters = ref<{ keyword: string; status: string }>({ keyword: '', status: '' })

const detail = ref<Row | null>(null)
const detailVersions = ref<Row[]>([])
const editing = ref<{ id: number; action: string; form: Row } | null>(null)
const creating = ref(false)
const createForm = ref<Row>({})

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function flashSuccess(message: string) {
  successMessage.value = message
  errorMessage.value = ''
}

async function reload() {
  errorMessage.value = ''
  successMessage.value = ''
  const params = new URLSearchParams()
  if (filters.value.keyword.trim()) params.set('keyword', filters.value.keyword.trim())
  if (filters.value.status) params.set('status', filters.value.status)
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('系统参数列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '系统设置列表读取失败'
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error(`系统参数详情读取失败（记录 #${row.id}）`)
    }
    detail.value = (await response.json()) as Row
    const params = new URLSearchParams({ keyword: String(detail.value['参数编码'] ?? ''), size: '200' })
    const versionResponse = await request(`${ENDPOINT}?${params.toString()}`)
    if (versionResponse.ok) {
      const payload = await versionResponse.json()
      detailVersions.value = (payload.items ?? []) as Row[]
    } else {
      detailVersions.value = []
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '系统参数详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
  detailVersions.value = []
}

function openCreate() {
  createForm.value = {}
  creating.value = true
}

function closeCreate() {
  creating.value = false
}

async function submitCreate() {
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.message ?? '系统参数登记失败')
    }
    creating.value = false
    flashSuccess(payload.message ?? '系统参数已登记')
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '系统参数登记失败'
  }
}

function openAction(action: string, row: Row) {
  errorMessage.value = ''
  if (action === '修改参数') {
    const form: Row = { 参数编码: row['参数编码'] ?? '' }
    for (const field of editFields) {
      form[field] = (row[field] ?? '') as string | number | null
    }
    editing.value = { id: Number(row.id), action, form }
    return
  }
  void runAction(action, row)
}

function closeEditor() {
  editing.value = null
}

async function submitEditor() {
  if (!editing.value) return
  const body = {
    action: editing.value.action,
    参数编码: editing.value.form['参数编码'],
    ...Object.fromEntries(editFields.map((field) => [field, editing.value?.form[field] ?? ''])),
  }
  try {
    const payload = await postAction(editing.value.id, body)
    editing.value = null
    flashSuccess(payload.message)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '系统参数修改失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const payload = await postAction(Number(row.id), { action })
    flashSuccess(payload.message)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '系统设置操作失败'
  }
}

async function postAction(entryId: number, values: Record<string, unknown>): Promise<{ ok: boolean; message: string }> {
  const response = await request(`${ENDPOINT}/${entryId}/actions`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  const payload = (await response.json()) as { ok?: boolean; message?: string }
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.message ?? '系统设置动作未生效，请稍后重试')
  }
  return { ok: true, message: payload.message ?? '操作成功' }
}

onMounted(reload)
</script>

<style scoped>
.is-current td { background: #eff6ff; }
</style>
