<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useLocaleText } from '../../../composables/useLocaleText'
import { apiFetch } from '@/api/client'

const { t, locale } = useI18n()
const { pickEn } = useLocaleText()
const message = useMessage()

function errOf(res: any, d: any): string {
  return d?.error || d?.detail || res.statusText || `HTTP ${res.status}`
}

// ── MCP 连接器 ──
const mcpConnectors = ref<any[]>([])
const showMcpModal = ref(false)
const mcpEditingId = ref<string | null>(null)  // null=无编辑, 'new'=新增, 其他=编辑某卡片
const mcpSaving = ref(false)
const mcpTab = ref<'form' | 'json'>('form')
const mcpForm = ref({ name: '', type: 'stdio', command: '', args: '', url: '', envText: '', headersText: '', description: '', descriptionEn: '' })
const deletingConn = ref<string | null>(null)

// ── 工具数据（合并自原 ToolsSection：按连接器分组，内嵌展示）──
const tools = ref<any[]>([])
const expandedConns = ref<Set<string>>(new Set())  // 展开工具列表的连接器名集合

async function loadTools() {
  try {
    const r = await apiFetch('/api/ai/tools')
    const d = await r.json()
    tools.value = d.tools || []
  } catch { /* ignore */ }
}

// 按连接器名分组工具
function toolsOf(connName: string): any[] {
  return tools.value.filter((t: any) => t.source === connName)
}

// 内置工具
const builtinTools = computed(() =>
  tools.value.filter((t: any) => t.source_type === 'builtin'))

// 工具状态点颜色
function toolDot(status: string): string {
  switch (status) {
    case 'available': case 'connected': return '#18a058'
    case 'cooldown': return '#f0a020'
    case 'disabled': return '#d03050'
    default: return '#909399'
  }
}

// 工具总数（含内置 + MCP）
const totalTools = computed(() => tools.value.length)

// 在线连接器数
const onlineConnectors = computed(() =>
  mcpConnectors.value.filter((c: any) => c.enabled).length)

function toggleExpand(name: string) {
  if (expandedConns.value.has(name)) expandedConns.value.delete(name)
  else expandedConns.value.add(name)
  // 触发响应式更新（Set 直接操作不触发）
  expandedConns.value = new Set(expandedConns.value)
}

// 来源平台徽章文案（全部走 i18n）
function platformLabel(p: string): string {
  const map: Record<string, string> = {
    smithery: 'ai.mcp.platform_smithery',
    modelscope: 'ai.mcp.platform_modelscope',
    mcpso: 'ai.mcp.platform_mcpso',
    paste: 'ai.mcp.platform_paste',
    curated: 'ai.mcp.platform_curated',
  }
  return t(map[p] || 'ai.mcp.platform_paste')
}

// 连接器卡片底部动作按钮文案：市场安装的叫「卸载」，手动添加的叫「删除」
function connActionLabel(c: any): string {
  return (c.source && c.source.platform) ? t('ai.mcp.uninstall_label') : t('ai.mcp.delete_label')
}

function needsCompletion(c: any): boolean {
  // env / headers 中含空值或 YOUR_ 占位符 → 待补全
  const isPlaceholder = (v: any) => v === '' || v == null || String(v).includes('YOUR_')
  const env = c.env || {}
  const headers = c.headers || {}
  return Object.values(env).some(isPlaceholder) || Object.values(headers).some(isPlaceholder)
}

// ── env 键值对编辑（每行 KEY=VALUE）──
function parseEnvText(text: string): Record<string, string> {
  const env: Record<string, string> = {}
  for (const line of (text || '').split('\n')) {
    const s = line.trim()
    if (!s || s.startsWith('#')) continue
    const idx = s.indexOf('=')
    if (idx <= 0) continue
    env[s.slice(0, idx).trim()] = s.slice(idx + 1).trim()
  }
  return env
}

function envToText(env: Record<string, string> | undefined | null): string {
  if (!env) return ''
  return Object.entries(env).map(([k, v]) => `${k}=${v ?? ''}`).join('\n')
}

async function loadMcpConnectors() {
  try {
    const r = await apiFetch('/api/mcp/connectors')
    const d = await r.json()
    mcpConnectors.value = d.connectors || []
  } catch (e) { /* ignore */ }
  // 同步刷新工具列表（连接器变化后工具归属也变）
  await loadTools()
}

function openMcpNew() {
  mcpEditingId.value = 'new'
  mcpTab.value = 'form'
  mcpForm.value = { name: '', type: 'stdio', command: '', args: '', url: '', envText: '', headersText: '', description: '', descriptionEn: '' }
  resetJsonTab()
  showMcpModal.value = true
}

function openMcpEdit(id: string) {
  const c = mcpConnectors.value.find(x => x.id === id)
  if (!c) return
  mcpEditingId.value = id
  mcpTab.value = 'form'
  mcpForm.value = {
    name: c.name || '',
    type: c.type || 'stdio',
    command: c.command || '',
    args: Array.isArray(c.args) ? c.args.join(', ') : (c.args || ''),
    url: c.url || '',
    envText: envToText(c.env),
    headersText: envToText(c.headers),
    description: c.description || '',
    descriptionEn: c.description_en || '',
  }
  resetJsonTab()
  showMcpModal.value = true
}

function cancelMcpEdit() {
  showMcpModal.value = false  // mcpEditingId 在 @after-leave 中重置，避免关闭动画期间标题闪变
}

async function saveMcpConnector() {
  if (!mcpForm.value.name) { message.warning(t('ai.mcp.name_required')); return }
  mcpSaving.value = true
  try {
    const body: any = { name: mcpForm.value.name, type: mcpForm.value.type }
    if (mcpForm.value.type === 'stdio') {
      body.command = mcpForm.value.command
      body.args = mcpForm.value.args.split(',').map(s => s.trim()).filter(Boolean)
    } else {
      body.url = mcpForm.value.url
    }
    const isNew = mcpEditingId.value === 'new'
    body.env = parseEnvText(mcpForm.value.envText)
    // 双语描述：description 为默认文案；description_en 为英文文案。
    // 英文环境下新增且未填英文描述 → 镜像默认描述，保证"英文新增默认英文展示"。
    body.description = mcpForm.value.description
    const existing = isNew ? null : mcpConnectors.value.find(x => x.id === mcpEditingId.value)
    body.description_en = mcpForm.value.descriptionEn
      || (locale.value === 'en-US' ? mcpForm.value.description : (existing?.description_en || ''))
    // 远程类型才带 headers（如 smithery 服务器的 X-TickDB-Key 走请求头传递）
    if (mcpForm.value.type !== 'stdio') {
      body.headers = parseEnvText(mcpForm.value.headersText)
    }
    const res = await apiFetch(isNew ? '/api/mcp/connectors' : `/api/mcp/connectors/${mcpEditingId.value}`, {
      method: isNew ? 'POST' : 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    let d: any = {}
    try { d = await res.json() } catch { /* 响应体非 JSON */ }
    // 同时检查 HTTP 状态码与响应体错误字段，避免失败时显示假成功消息
    if (!res.ok || d.error || d.detail) {
      const detail = d.error || d.detail || res.statusText || `HTTP ${res.status}`
      message.error(t('ai.save_failed', { error: detail }))
      return
    }
    message.success(isNew ? t('ai.mcp.added') : t('ai.mcp.updated'))
    showMcpModal.value = false  // 仅关闭 Modal；mcpEditingId 在 @after-leave 中重置，避免标题闪变
    await loadMcpConnectors()
  } catch (e: any) { message.error(t('ai.save_failed', { error: e.message || '' })) }
  finally { mcpSaving.value = false }
}

async function deleteMcpConnector(id: string) {
  deletingConn.value = id
  try {
    await apiFetch(`/api/mcp/connectors/${id}`, { method: 'DELETE' })
    message.success(t('ai.mcp.deleted'))
    await loadMcpConnectors()
  } catch { message.error(t('ai.delete_failed')) }
  finally { deletingConn.value = null }
}

async function toggleMcpConnector(id: string) {
  try {
    await apiFetch(`/api/mcp/connectors/${id}/toggle`, { method: 'POST' })
    await loadMcpConnectors()
  } catch { message.error(t('ai.mcp.toggle_failed')) }
}

// ── JSON 导入（编辑 Modal 内的标签页）──
const jsonText = ref('')
const jsonPolicy = ref('skip')
const jsonParsing = ref(false)
const jsonPreview = ref<any | null>(null)   // {ok: [...], errors: [...]}
const jsonImporting = ref(false)
const jsonResults = ref<any[]>([])          // 导入后的逐条结果

const policyOptions = computed(() => [
  { label: t('ai.policy_skip'), value: 'skip' },
  { label: t('ai.policy_overwrite'), value: 'overwrite' },
  { label: t('ai.policy_rename'), value: 'rename' },
])

function resetJsonTab() {
  jsonText.value = ''
  jsonPreview.value = null
  jsonResults.value = []
}

async function parseJsonPreview() {
  const text = jsonText.value.trim()
  if (!text) { message.warning(t('ai.mcp.paste_json_required')); return }
  jsonParsing.value = true
  jsonPreview.value = null
  jsonResults.value = []
  try {
    const res = await apiFetch('/api/mcp/store/parse-json', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw: text }),
    })
    let d: any = {}
    try { d = await res.json() } catch { /* ignore */ }
    if (!res.ok) { message.error(t('ai.mcp.parse_failed', { error: errOf(res, d) })); return }
    jsonPreview.value = d
  } catch { message.error(t('ai.mcp.parse_request_failed')) }
  finally { jsonParsing.value = false }
}

async function doJsonImport(text: string, policy: string, platform: string): Promise<any | null> {
  try {
    const res = await apiFetch('/api/mcp/store/import-json', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw: text, conflict_policy: policy, platform }),
    })
    let d: any = {}
    try { d = await res.json() } catch { /* ignore */ }
    if (!res.ok || !d.ok) { message.error(t('ai.mcp.import_failed', { error: errOf(res, d) })); return null }
    return d
  } catch { message.error(t('ai.mcp.import_request_failed')); return null }
}

// 导入结果摘要文案（含覆盖/跳过数量）
function importSummary(d: any): string {
  const parts = [t('ai.mcp.import_done', { n: d.imported || 0 })]
  if (d.overwritten) parts.push(t('ai.mcp.import_overwritten', { n: d.overwritten }))
  if (d.skipped) parts.push(t('ai.mcp.import_skipped', { n: d.skipped }))
  return parts.join('')
}

async function importJsonTab() {
  const text = jsonText.value.trim()
  if (!text) { message.warning(t('ai.mcp.paste_json_required')); return }
  jsonImporting.value = true
  jsonResults.value = []
  try {
    const d = await doJsonImport(text, jsonPolicy.value, 'paste')
    if (!d) return
    jsonResults.value = [...(d.results || []), ...((d.parse_errors || []).map((e: any) =>
      ({ name: e.name || t('ai.mcp.overall'), action: 'error', error: e.reason })))]
    jsonPreview.value = null
    message.success(importSummary(d))
    await loadMcpConnectors()
  } finally { jsonImporting.value = false }
}

function actionLabel(r: any): string {
  switch (r.action) {
    case 'imported': return t('ai.mcp.act_imported')
    case 'renamed': return t('ai.mcp.act_renamed', { name: r.final_name || '' })
    case 'overwritten': return t('ai.mcp.act_overwritten')
    case 'skipped': return t('ai.mcp.act_skipped', { reason: r.reason || t('ai.mcp.act_duplicate') })
    case 'error': return t('ai.mcp.act_error', { error: r.error || t('ai.unknown') })
    default: return r.action
  }
}

function actionColor(r: any): string {
  if (['imported', 'renamed', 'overwritten'].includes(r.action)) return '#18a058'
  if (r.action === 'skipped') return '#f0a020'
  return '#d03050'
}

// 解析预览摘要文案
function importPreviewText(p: any): string {
  const n = p.ok?.length || 0
  const errs = p.errors?.length ? t('ai.mcp.import_errors_suffix', { n: p.errors.length }) : ''
  return t('ai.mcp.import_preview', { n, errors: errs })
}

// ── 市场 Modal ──
const showMarketModal = ref(false)
const platforms = ref<any[]>([])
const selectedPlatform = ref('smithery')
const loadingPlatforms = ref(false)

// Smithery API Key（Agent 设置，打码显示）
const smitheryKey = ref('')
const smitheryKeySaving = ref(false)
const smitheryKeyConfigured = ref(false)
const smitheryKeyMasked = ref('')

async function loadAgentSettings() {
  try {
    const res = await apiFetch('/api/ai/agent-settings')
    if (!res.ok) return
    const d = await res.json()
    smitheryKeyConfigured.value = !!d.smithery_api_key_configured
    smitheryKeyMasked.value = d.smithery_api_key || ''
  } catch { /* ignore */ }
}

async function loadPlatforms() {
  const r = await apiFetch('/api/mcp/store/platforms')
  const d = await r.json()
  platforms.value = d.platforms || []
}

async function saveSmitheryKey() {
  const val = smitheryKey.value.trim()
  if (!val) { message.warning(t('ai.smithery_key_empty_hint')); return }
  smitheryKeySaving.value = true
  try {
    const res = await apiFetch('/api/ai/agent-settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ smithery_api_key: val }),
    })
    let d: any = {}
    try { d = await res.json() } catch { /* 响应体非 JSON */ }
    if (!res.ok || d.error || d.detail) {
      message.error(`${t('ai.save_failed', { error: '' })}: ${errOf(res, d)}`)
      return
    }
    smitheryKey.value = ''
    smitheryKeyConfigured.value = !!d.smithery_api_key_configured
    smitheryKeyMasked.value = d.smithery_api_key || ''
    message.success(t('ai.saved'))
    // 刷新平台列表：smithery 从直链模式切换为系统内搜索模式
    try { await loadPlatforms() } catch { /* ignore */ }
  } catch { message.error(t('ai.save_failed', { error: '' })) }
  finally { smitheryKeySaving.value = false }
}

async function clearSmitheryKey() {
  smitheryKeySaving.value = true
  try {
    const res = await apiFetch('/api/ai/agent-settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ smithery_api_key: '' }),
    })
    let d: any = {}
    try { d = await res.json() } catch { /* 响应体非 JSON */ }
    if (!res.ok || d.error || d.detail) {
      message.error(`${t('ai.save_failed', { error: '' })}: ${errOf(res, d)}`)
      return
    }
    smitheryKey.value = ''
    smitheryKeyConfigured.value = false
    smitheryKeyMasked.value = ''
    message.success(t('ai.smithery_key_cleared'))
    try { await loadPlatforms() } catch { /* ignore */ }
  } catch { message.error(t('ai.save_failed', { error: '' })) }
  finally { smitheryKeySaving.value = false }
}

// smithery 搜索
const searchQuery = ref('')
const searching = ref(false)
const searchResults = ref<any[]>([])
const searchError = ref('')
const searchDone = ref(false)
const installingQn = ref('')

// 粘贴导入区（smithery 无 Key / mcp.so 共用）
const mkPasteText = ref('')
const mkPastePolicy = ref('skip')
const mkPasteImporting = ref(false)
const mkPasteResults = ref<any[]>([])

// 魔搭模板
const msTemplates = ref<any[]>([])
const tplValues = ref<Record<string, Record<string, string>>>({})
const installingTpl = ref('')

// 平台等级标签文案
function platformLevelLabel(p: any): string {
  if (p.level === 'api') return t('ai.mcp.level_api')
  if (p.level === 'template') return t('ai.mcp.level_template')
  return t('ai.mcp.level_browse')
}

const currentPlatform = computed(() =>
  platforms.value.find((p: any) => p.id === selectedPlatform.value))

async function openMarketModal() {
  showMarketModal.value = true
  searchError.value = ''
  mkPasteResults.value = []
  if (!platforms.value.length) {
    loadingPlatforms.value = true
    try {
      await loadPlatforms()
    } catch { message.error(t('ai.mcp.platforms_load_failed')) }
    finally { loadingPlatforms.value = false }
  }
  await loadAgentSettings()
  if (!msTemplates.value.length) {
    try {
      const r = await apiFetch('/api/mcp/store/templates')
      const d = await r.json()
      msTemplates.value = d.templates || []
      for (const tpl of msTemplates.value) {
        tplValues.value[tpl.id] = {}
        for (const f of (tpl.fields || [])) tplValues.value[tpl.id][f.key] = ''
      }
    } catch { /* ignore */ }
  }
}

function openPlatform(url: string) {
  window.open(url, '_blank')
}

async function doSmitherySearch() {
  const q = searchQuery.value.trim()
  if (!q) { message.warning(t('ai.mcp.search_required')); return }
  searching.value = true
  searchError.value = ''
  searchResults.value = []
  searchDone.value = false
  try {
    const res = await apiFetch(`/api/mcp/store/search?platform=smithery&q=${encodeURIComponent(q)}`)
    let d: any = {}
    try { d = await res.json() } catch { /* ignore */ }
    if (!res.ok) { searchError.value = errOf(res, d); return }
    searchResults.value = d.results || []
    searchDone.value = true
  } catch { searchError.value = t('ai.mcp.search_error') }
  finally { searching.value = false }
}

async function installSmithery(item: any) {
  installingQn.value = item.qualifiedName || item.name
  try {
    const res = await apiFetch(`/api/mcp/store/detail?platform=smithery&qualified_name=${encodeURIComponent(item.qualifiedName || item.name)}`)
    let d: any = {}
    try { d = await res.json() } catch { /* ignore */ }
    if (!res.ok || !d.connectors?.length) { message.error(t('ai.mcp.detail_failed', { error: errOf(res, d) })); return }
    // 把后端转换好的连接器重新打包为 mcpServers JSON，走统一导入链路
    const servers: Record<string, any> = {}
    for (const c of d.connectors) {
      servers[c.name] = {
        type: c.type, command: c.command || undefined, args: c.args?.length ? c.args : undefined,
        url: c.url || undefined, env: Object.keys(c.env || {}).length ? c.env : undefined,
        headers: Object.keys(c.headers || {}).length ? c.headers : undefined,
        description: c.description || undefined,
      }
    }
    const imp = await doJsonImport(JSON.stringify({ mcpServers: servers }, null, 2), 'rename', 'smithery')
    if (!imp) return
    let msg = t('ai.mcp.installed', { name: item.name, n: imp.imported, skipped: '' })
    if (imp.skipped) msg += t('ai.mcp.import_skipped', { n: imp.skipped })
    message.success(msg)
    // 必填凭据（如 X-TickDB-Key）留空占位 → 明确告知需补充，避免「装上了却连不通」
    const need = (d.connectors || []).flatMap((c: any) => c.required_config || [])
    if (need.length) {
      const names = need.map((n: any) => `${n.name}(${n.target === 'header' ? t('ai.mcp.headers') : t('ai.mcp.env')})`).join('、')
      message.warning(t('ai.mcp.need_config', { names }), { duration: 8000 })
    }
    await loadMcpConnectors()
  } catch { message.error(t('ai.mcp.install_failed')) }
  finally { installingQn.value = '' }
}

async function mkPasteImport(platform: string) {
  const text = mkPasteText.value.trim()
  if (!text) { message.warning(t('ai.mcp.paste_json_required')); return }
  mkPasteImporting.value = true
  mkPasteResults.value = []
  try {
    const d = await doJsonImport(text, mkPastePolicy.value, platform)
    if (!d) return
    mkPasteResults.value = [...(d.results || []), ...((d.parse_errors || []).map((e: any) =>
      ({ name: e.name || t('ai.mcp.overall'), action: 'error', error: e.reason })))]
    message.success(importSummary(d))
    mkPasteText.value = ''
    await loadMcpConnectors()
  } finally { mkPasteImporting.value = false }
}

async function installTemplate(tpl: any) {
  const vals = tplValues.value[tpl.id] || {}
  const name = (vals['name'] || '').trim()
  if (!name) { message.warning(t('ai.mcp.name_required')); return }
  installingTpl.value = tpl.id
  try {
    const cfg: any = {}
    const env: Record<string, string> = {}
    for (const f of (tpl.fields || [])) {
      const v = (vals[f.key] || '').trim()
      if (f.key === 'name') continue
      if (f.key === 'url') cfg.url = v
      else if (f.key.startsWith('env.')) env[f.key.slice(4)] = v
    }
    if (tpl.type === 'stdio') { cfg.command = tpl.command; cfg.args = tpl.args || [] }
    if (Object.keys(env).length) cfg.env = env
    // 必填校验
    if (tpl.type === 'sse' && !cfg.url) { message.warning(t('ai.mcp.sse_url_required')); return }
    for (const f of (tpl.fields || [])) {
      if (f.key.startsWith('env.') && !(vals[f.key] || '').trim()) {
        message.warning(t('ai.mcp.fill_field', { field: f.label })); return
      }
    }
    const d = await doJsonImport(JSON.stringify({ mcpServers: { [name]: cfg } }, null, 2), 'rename', 'modelscope')
    if (!d) return
    message.success(t('ai.mcp.installed_one', { name }))
    tplValues.value[tpl.id] = Object.fromEntries((tpl.fields || []).map((f: any) => [f.key, '']))
    await loadMcpConnectors()
  } finally { installingTpl.value = '' }
}

// 类型选项（写死但文案走 i18n）
const mcpTypeOptions = computed(() => ([
  { label: t('ai.mcp.type_stdio'), value: 'stdio' },
  { label: t('ai.mcp.type_sse'), value: 'sse' },
  { label: t('ai.mcp.type_http'), value: 'http' },
]))

onMounted(loadMcpConnectors)
</script>

<template>
  <n-card size="small" :bordered="true">
    <template #header>
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <span>{{ t('ai.mcp.header', { connectors: mcpConnectors.length, tools: totalTools }) }}</span>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
          <n-tag v-if="mcpConnectors.length" size="tiny" :bordered="false" type="info">
            {{ t('ai.mcp.enabled_count', { online: onlineConnectors, total: mcpConnectors.length }) }}
          </n-tag>
          <n-button size="tiny" quaternary @click="loadMcpConnectors">{{ t('common.refresh') }}</n-button>
        </div>
      </div>
    </template>
    <!-- 统一卡片网格：--tile-h 固定行高 → 所有卡片等宽等高；
         内容超出在 .tile-bd 内部纵向滚动，不再溢出遮挡相邻/下方卡片。 -->
    <div class="tile-grid" style="--tile-h:210px">
      <div v-for="c in mcpConnectors" :key="c.id"
        class="tile tile-click" :class="c.enabled ? 'tile-on' : 'tile-off'"
        @click="openMcpEdit(c.id)">
        <!-- 头部：名称 + 启用开关（固定） -->
        <div class="tile-hd u-row">
          <span class="u-break" :title="c.name"
            style="font-weight:600;font-size:15px;line-height:1.25">{{ c.name }}</span>
          <div @click.stop style="flex-shrink:0">
            <n-switch :value="!!c.enabled" size="small" @update:value="() => toggleMcpConnector(c.id)" :round="true" />
          </div>
        </div>
        <!-- 主体：唯一滚动区 -->
        <div class="tile-bd">
          <!-- 类型 + 来源 + 待补全 标签 -->
          <div class="u-tags" style="margin-bottom:6px">
            <n-tag :bordered="false" size="tiny" :type="c.type === 'stdio' ? 'info' : 'success'">{{ c.type }}</n-tag>
            <n-tag v-if="c.source && c.source.platform" :bordered="false" size="tiny" type="success">
              {{ platformLabel(c.source.platform) }}
            </n-tag>
            <n-tag v-if="needsCompletion(c)" :bordered="false" size="tiny" type="warning">{{ t('ai.mcp.needs_completion') }}</n-tag>
          </div>
          <!-- 描述（完整显示，超出由卡片滚动条负责） -->
          <div v-if="pickEn(c)" style="font-size:12px;opacity:0.7;line-height:1.45;margin-bottom:8px">
            {{ pickEn(c) }}
          </div>
          <!-- URL 或 Command -->
          <div class="u-break" style="font-size:11px;color:#8b8f97;margin-bottom:8px">
            {{ (c.type === 'sse' || c.type === 'http') ? (c.url || '') : [c.command, ...(Array.isArray(c.args) ? c.args : [])].filter(Boolean).join(' ') }}
          </div>
          <!-- 工具展开区（@click.stop 防止触发卡片编辑） -->
          <div v-if="toolsOf(c.name).length > 0" @click.stop style="margin-bottom:4px">
            <div @click="toggleExpand(c.name)"
              style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;color:#8b8f97;user-select:none;padding:2px 0">
              <span>{{ expandedConns.has(c.name) ? '▾' : '▸' }}</span>
              <span>{{ t('ai.mcp.tools_label', { n: toolsOf(c.name).length }) }}</span>
              <span v-if="toolsOf(c.name).some((t:any)=>t.status==='connected'||t.status==='available')"
                style="width:6px;height:6px;border-radius:50%;background:#18a058;display:inline-block;flex-shrink:0" />
            </div>
            <div v-if="expandedConns.has(c.name)"
              style="margin-top:6px;display:flex;flex-direction:column;gap:4px">
              <div v-for="tl in toolsOf(c.name)" :key="tl.name"
                style="display:flex;align-items:flex-start;gap:6px;padding:4px 6px;border-radius:4px;background:rgba(128,128,128,0.06)">
                <span :style="{ width:'6px',height:'6px',borderRadius:'50%',background:toolDot(tl.status),marginTop:'5px',flexShrink:'0' }" />
                <div style="flex:1;min-width:0">
                  <div class="u-break" style="font-size:12px;font-weight:500">{{ tl.orig_name || tl.name }}</div>
                  <div v-if="pickEn(tl)" style="font-size:10px;opacity:0.6;line-height:1.35">{{ pickEn(tl) }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <!-- 底部：编辑提示 + 卸载/删除按钮（固定） -->
        <div class="tile-ft u-row">
          <span style="font-size:10px;opacity:0.4">{{ t('ai.mcp.click_to_edit') }}</span>
          <div @click.stop style="flex-shrink:0">
            <n-popconfirm @positive-click="deleteMcpConnector(c.id)">
              <template #trigger>
                <n-button size="tiny" quaternary type="error" :loading="deletingConn === c.id">{{ connActionLabel(c) }}</n-button>
              </template>
              {{ t('ai.mcp.confirm_delete_connector', { name: c.name }) }}
            </n-popconfirm>
          </div>
        </div>
      </div>

      <!-- 系统内置工具卡片（非 MCP，系统自带能力） -->
      <div v-if="builtinTools.length > 0" class="tile">
        <div class="tile-hd u-row">
          <span style="font-weight:600;font-size:15px">{{ t('ai.mcp.builtin_title') }}</span>
          <n-tag :bordered="false" size="tiny" type="success">{{ t('ai.mcp.always_available') }}</n-tag>
        </div>
        <div class="tile-bd">
          <div class="u-tags" style="margin-bottom:6px">
            <n-tag :bordered="false" size="tiny" type="success">builtin</n-tag>
          </div>
          <div style="font-size:12px;opacity:0.7;line-height:1.45;margin-bottom:8px">
            {{ t('ai.mcp.builtin_desc') }}
          </div>
          <div @click="toggleExpand('__builtin__')"
            style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;color:#8b8f97;user-select:none;padding:2px 0">
            <span>{{ expandedConns.has('__builtin__') ? '▾' : '▸' }}</span>
            <span>{{ t('ai.mcp.tools_label', { n: builtinTools.length }) }}</span>
            <span style="width:6px;height:6px;border-radius:50%;background:#18a058;display:inline-block;flex-shrink:0" />
          </div>
          <div v-if="expandedConns.has('__builtin__')"
            style="margin-top:6px;display:flex;flex-direction:column;gap:4px">
            <div v-for="tl in builtinTools" :key="tl.name"
              style="display:flex;align-items:flex-start;gap:6px;padding:4px 6px;border-radius:4px;background:rgba(128,128,128,0.06)">
              <span style="width:6px;height:6px;border-radius:50%;background:#18a058;margin-top:5px;flex-shrink:0" />
              <div style="flex:1;min-width:0">
                <div class="u-break" style="font-size:12px;font-weight:500">{{ tl.name }}</div>
                <div v-if="pickEn(tl)" style="font-size:10px;opacity:0.6;line-height:1.35">{{ pickEn(tl) }}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="tile-ft u-row">
          <span style="font-size:10px;opacity:0.4">{{ t('ai.mcp.builtin_footer') }}</span>
        </div>
      </div>

      <!-- 新增连接器空白卡片 -->
      <div v-if="!showMcpModal" class="tile tile-dash tile-click" @click="openMcpNew">
        <span style="font-size:26px;color:#8b8f97;line-height:1">+</span>
        <span style="font-size:13px;color:#8b8f97">{{ t('ai.mcp.add_connector') }}</span>
      </div>

      <!-- 从市场添加卡片 -->
      <div v-if="!showMcpModal" class="tile tile-dash tile-click" @click="openMarketModal">
        <span style="font-size:22px;color:#8b8f97;line-height:1">🛒</span>
        <span style="font-size:13px;color:#8b8f97">{{ t('ai.mcp.add_from_market') }}</span>
      </div>
    </div>

    <!-- MCP 连接器编辑 Modal（表单 / JSON 导入 双标签页） -->
    <n-modal v-model:show="showMcpModal" :mask-closable="false" preset="card" style="max-width:680px" @after-leave="mcpEditingId = null" :title="mcpEditingId === 'new' ? t('ai.mcp.new_connector') : t('ai.mcp.edit_connector')">
      <n-tabs v-model:value="mcpTab" type="line" animated size="small">
        <!-- ══ 表单标签页 ══ -->
        <n-tab-pane name="form" :tab="t('ai.mcp.tab_form')">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px">
            <div>
              <div style="font-size:12px;color:#8b8f97;margin-bottom:4px">{{ t('ai.name') }}</div>
              <n-input v-model:value="mcpForm.name" size="small" :placeholder="t('ai.mcp.name_ph')" />
            </div>
            <div>
              <div style="font-size:12px;color:#8b8f97;margin-bottom:4px">{{ t('ai.type') }}</div>
              <n-select v-model:value="mcpForm.type" size="small" :options="mcpTypeOptions" />
            </div>
            <div v-if="mcpForm.type === 'stdio'" style="grid-column:span 2">
              <div style="font-size:12px;color:#8b8f97;margin-bottom:4px">{{ t('ai.mcp.command') }}</div>
              <n-input v-model:value="mcpForm.command" size="small" :placeholder="t('ai.mcp.name_ph')" />
            </div>
            <div v-if="mcpForm.type === 'stdio'" style="grid-column:span 2">
              <div style="font-size:12px;color:#8b8f97;margin-bottom:4px">{{ t('ai.mcp.args') }}</div>
              <n-input v-model:value="mcpForm.args" size="small" :placeholder="t('ai.mcp.name_ph')" />
            </div>
            <div v-if="mcpForm.type === 'sse' || mcpForm.type === 'http'" style="grid-column:span 2">
              <div style="font-size:12px;color:#8b8f97;margin-bottom:4px">{{ t('ai.mcp.url') }}</div>
              <n-input v-model:value="mcpForm.url" size="small" :placeholder="t('ai.mcp.url_ph')" />
            </div>
            <div v-if="mcpForm.type !== 'stdio'" style="grid-column:span 2">
              <div style="font-size:12px;color:#8b8f97;margin-bottom:4px">{{ t('ai.mcp.headers') }}</div>
              <n-input v-model:value="mcpForm.headersText" size="small" type="textarea" :rows="2"
                :placeholder="t('ai.mcp.headers_ph')" />
            </div>
            <div style="grid-column:span 2">
              <div style="font-size:12px;color:#8b8f97;margin-bottom:4px">{{ t('ai.mcp.env') }}</div>
              <n-input v-model:value="mcpForm.envText" size="small" type="textarea" :rows="3"
                :placeholder="t('ai.mcp.env_ph')" />
            </div>
            <div style="grid-column:span 2">
              <div style="font-size:12px;color:#8b8f97;margin-bottom:4px">{{ t('ai.mcp.desc') }}</div>
              <n-input v-model:value="mcpForm.description" size="small" type="textarea" :rows="2"
                :placeholder="t('ai.mcp.desc_ph')" />
            </div>
            <div style="grid-column:span 2">
              <div style="font-size:12px;color:#8b8f97;margin-bottom:4px">{{ t('ai.mcp.desc_en') }}</div>
              <n-input v-model:value="mcpForm.descriptionEn" size="small" type="textarea" :rows="2"
                :placeholder="t('ai.mcp.desc_en_ph')" />
            </div>
          </div>
        </n-tab-pane>

        <!-- ══ JSON 导入标签页 ══ -->
        <n-tab-pane name="json" :tab="t('ai.mcp.tab_json')">
          <n-alert type="info" :bordered="false" style="margin:8px 0">
            {{ t('ai.mcp.json_hint') }}
            <code>{"mcpServers": {"fs": {"command": "npx", "args": [...]}}}</code>
          </n-alert>
          <n-input v-model:value="jsonText" type="textarea" :rows="7"
            :placeholder="t('ai.mcp.json_example')" />
          <div style="display:flex;align-items:center;justify-content:space-between;margin-top:10px;flex-wrap:wrap;gap:8px">
            <n-radio-group v-model:value="jsonPolicy" size="small">
              <n-radio-button v-for="opt in policyOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </n-radio-button>
            </n-radio-group>
            <n-space size="small">
              <n-button size="small" :loading="jsonParsing" @click="parseJsonPreview">{{ t('ai.mcp.parse_preview') }}</n-button>
              <n-button size="small" type="primary" :loading="jsonImporting" @click="importJsonTab">{{ t('ai.mcp.import') }}</n-button>
            </n-space>
          </div>

          <!-- 解析预览 -->
          <div v-if="jsonPreview" style="margin-top:12px">
            <n-text depth="3" style="font-size:12px">
              {{ importPreviewText(jsonPreview) }}
            </n-text>
            <div v-for="c in jsonPreview.ok" :key="'pv-' + c.name" class="preview-row" style="border-left:3px solid #18a058">
              <n-tag size="tiny" :bordered="false" :type="c.type === 'stdio' ? 'info' : 'success'">{{ c.type }}</n-tag>
              <b style="margin-left:6px">{{ c.name }}</b>
              <span style="opacity:0.65;margin-left:8px;font-size:12px">
                {{ (c.type === 'sse' || c.type === 'http') ? c.url : [c.command, ...(c.args || [])].filter(Boolean).join(' ') }}
              </span>
            </div>
            <div v-for="(e, i) in jsonPreview.errors" :key="'pe-' + i" class="preview-row" style="border-left:3px solid #d03050;color:#d03050">
              <b style="margin-right:6px">{{ e.name || t('ai.mcp.overall') }}</b>{{ e.reason }}
            </div>
          </div>

          <!-- 导入逐条结果 -->
          <div v-if="jsonResults.length" style="margin-top:12px">
            <n-text depth="3" style="font-size:12px">{{ t('ai.mcp.import_result') }}</n-text>
            <div v-for="(r, i) in jsonResults" :key="'jr-' + i" class="preview-row"
              :style="{ borderLeft: `3px solid ${actionColor(r)}`, color: actionColor(r) }">
              <b style="margin-right:6px">{{ r.name }}</b>{{ actionLabel(r) }}
            </div>
          </div>
        </n-tab-pane>
      </n-tabs>

      <template #footer>
        <div v-if="mcpTab === 'form'" style="display:flex;justify-content:flex-end;gap:8px">
          <n-button size="small" quaternary @click="cancelMcpEdit">{{ t('ai.cancel') }}</n-button>
          <n-button type="primary" size="small" @click="saveMcpConnector" :loading="mcpSaving">{{ t('ai.save') }}</n-button>
        </div>
        <div v-else style="display:flex;justify-content:flex-end">
          <n-button size="small" quaternary @click="cancelMcpEdit">{{ t('common.close') }}</n-button>
        </div>
      </template>
    </n-modal>

    <!-- ══ MCP 市场 Modal ══ -->
    <n-modal v-model:show="showMarketModal" preset="card" :title="t('ai.mcp.market_title')"
      style="width: 760px; max-width: 94vw">
      <n-spin :show="loadingPlatforms">
        <n-grid :cols="3" :x-gap="10" :y-gap="10" responsive="screen" item-responsive>
          <n-gi v-for="p in platforms" :key="p.id" span="3 m:1">
            <div class="platform-card" :class="{ active: selectedPlatform === p.id }"
              @click="selectedPlatform = p.id">
              <div class="platform-top">
                <span class="platform-name">{{ pickEn(p, 'name') }}</span>
                <n-tag size="tiny" :type="p.level === 'api' ? 'success' : (p.level === 'template' ? 'info' : 'default')" :bordered="false">
                  {{ p.grade }} {{ t('ai.grade_unit') }} · {{ platformLevelLabel(p) }}
                </n-tag>
              </div>
              <div class="platform-desc">{{ pickEn(p) }}</div>
              <n-button size="tiny" quaternary @click.stop="openPlatform(p.url)">{{ t('ai.mcp.open_platform') }}</n-button>
            </div>
          </n-gi>
        </n-grid>
      </n-spin>

      <n-divider style="margin: 14px 0" />

      <!-- ── Smithery：有 Key 系统内搜索 / 无 Key 粘贴引导 ── -->
      <div v-if="selectedPlatform === 'smithery'">
        <!-- Smithery API Key 配置区 -->
        <div style="border:1px solid rgba(128,128,128,0.25);border-radius:8px;padding:12px;margin-bottom:12px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;flex-wrap:wrap;gap:6px">
            <span style="font-weight:600;font-size:13px">{{ t('ai.smithery_key_title') }}</span>
            <n-tag v-if="smitheryKeyConfigured" size="tiny" :bordered="false" type="success">
              {{ t('ai.smithery_key_configured') }}{{ smitheryKeyMasked ? `（${smitheryKeyMasked}）` : '' }}
            </n-tag>
            <n-tag v-else size="tiny" :bordered="false" type="warning">{{ t('ai.smithery_key_not_configured') }}</n-tag>
          </div>
          <n-input-group>
            <n-input v-model:value="smitheryKey" type="password" show-password-on="click"
              :placeholder="smitheryKeyConfigured ? t('ai.keep_empty') : t('ai.smithery_key_placeholder')"
              style="flex:1" @keydown.enter="saveSmitheryKey" />
            <n-button type="primary" :loading="smitheryKeySaving" @click="saveSmitheryKey">{{ t('ai.save') }}</n-button>
            <n-button :disabled="!smitheryKeyConfigured || smitheryKeySaving" @click="clearSmitheryKey">{{ t('ai.smithery_key_clear') }}</n-button>
          </n-input-group>
        </div>

        <template v-if="currentPlatform?.level === 'api'">
          <n-input-group>
            <n-input v-model:value="searchQuery" :placeholder="t('ai.mcp.search_ph')"
              clearable @keydown.enter="doSmitherySearch" />
            <n-button type="primary" :loading="searching" @click="doSmitherySearch">{{ t('ai.mcp.search') }}</n-button>
          </n-input-group>
          <div style="margin-top:12px">
            <n-spin :show="searching">
              <n-alert v-if="searchError" type="warning" :bordered="false" style="margin-bottom:8px">
                {{ searchError }}
              </n-alert>
              <n-empty v-else-if="searchDone && searchResults.length === 0" size="small" :description="t('ai.mcp.no_results')" />
              <n-space vertical v-if="searchResults.length > 0" size="small">
                <n-card v-for="item in searchResults" :key="item.qualifiedName || item.name" size="small">
                  <template #header>
                    <span style="font-weight:600">{{ item.name }}</span>
                    <n-text depth="3" style="font-size:11px;margin-left:8px">{{ item.qualifiedName }}</n-text>
                  </template>
                  <template #header-extra>
                    <n-button size="tiny" type="primary" secondary
                      :loading="installingQn === (item.qualifiedName || item.name)"
                      @click="installSmithery(item)">{{ t('ai.mcp.install') }}</n-button>
                  </template>
                  <span class="result-desc">{{ pickEn(item) }}</span>
                </n-card>
              </n-space>
            </n-spin>
          </div>
        </template>
        <template v-else>
          <n-alert type="warning" :bordered="false" style="margin-bottom:8px">
            {{ t('ai.mcp.smithery_no_key_hint') }}
          </n-alert>
          <n-input v-model:value="mkPasteText" type="textarea" :rows="6"
            :placeholder="t('ai.mcp.json_example_smithery')" />
          <div style="display:flex;align-items:center;justify-content:space-between;margin-top:10px;flex-wrap:wrap;gap:8px">
            <n-radio-group v-model:value="mkPastePolicy" size="small">
              <n-radio-button v-for="opt in policyOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</n-radio-button>
            </n-radio-group>
            <n-button type="primary" size="small" :loading="mkPasteImporting" @click="mkPasteImport('smithery')">{{ t('ai.mcp.import') }}</n-button>
          </div>
        </template>
      </div>

      <!-- ── 魔搭：预置模板 ── -->
      <div v-else-if="selectedPlatform === 'modelscope'">
        <n-space vertical size="medium">
          <n-card v-for="tpl in msTemplates" :key="tpl.id" size="small" :title="pickEn(tpl, 'title')">
            <template #header-extra>
              <n-tag size="tiny" :bordered="false" :type="tpl.type === 'sse' ? 'success' : 'info'">{{ tpl.type }}</n-tag>
            </template>
            <div style="font-size:12px;opacity:0.75;margin-bottom:10px">{{ pickEn(tpl) }}</div>
            <n-space vertical size="small">
              <div v-for="f in tpl.fields" :key="f.key">
                <div style="font-size:12px;color:#8b8f97;margin-bottom:3px">{{ pickEn(f, 'label') }}</div>
                <n-input v-model:value="tplValues[tpl.id][f.key]" size="small"
                  :type="f.secret ? 'password' : 'text'" :placeholder="f.placeholder" />
              </div>
            </n-space>
            <n-text depth="3" style="font-size:11px;display:block;margin-top:8px">{{ pickEn(tpl, 'note') }}</n-text>
            <div style="margin-top:10px;display:flex;justify-content:space-between;align-items:center">
              <n-button size="tiny" quaternary @click="openPlatform(tpl.platform_url)">{{ t('ai.mcp.open_modelscope') }}</n-button>
              <n-button size="small" type="primary" :loading="installingTpl === tpl.id"
                @click="installTemplate(tpl)">{{ t('ai.mcp.install') }}</n-button>
            </div>
          </n-card>
        </n-space>
      </div>

      <!-- ── mcp.so：直连跳转 + 粘贴导入 ── -->
      <div v-else-if="selectedPlatform === 'mcpso'">
        <n-alert type="info" :bordered="false" style="margin-bottom:8px">
          {{ t('ai.mcp.mcpso_hint') }}
        </n-alert>
        <n-input v-model:value="mkPasteText" type="textarea" :rows="6"
          :placeholder="t('ai.mcp.json_example_mcpso')" />
        <div style="display:flex;align-items:center;justify-content:space-between;margin-top:10px;flex-wrap:wrap;gap:8px">
          <n-radio-group v-model:value="mkPastePolicy" size="small">
            <n-radio-button v-for="opt in policyOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</n-radio-button>
          </n-radio-group>
          <n-button type="primary" size="small" :loading="mkPasteImporting" @click="mkPasteImport('mcpso')">{{ t('ai.mcp.import') }}</n-button>
        </div>
      </div>

      <!-- 市场导入逐条结果 -->
      <div v-if="mkPasteResults.length" style="margin-top:12px">
        <n-text depth="3" style="font-size:12px">{{ t('ai.mcp.import_result') }}</n-text>
        <div v-for="(r, i) in mkPasteResults" :key="'mr-' + i" class="preview-row"
          :style="{ borderLeft: `3px solid ${actionColor(r)}`, color: actionColor(r) }">
          <b style="margin-right:6px">{{ r.name }}</b>{{ actionLabel(r) }}
        </div>
      </div>
    </n-modal>
  </n-card>
</template>

<style scoped>
.platform-card {
  border: 1px solid rgba(128, 128, 128, 0.25);
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  display: flex;
  flex-direction: column;
  gap: 6px;
  height: 100%;
}
.platform-card:hover {
  border-color: rgba(240, 185, 11, 0.6);
}
.platform-card.active {
  border-color: #f0b90b;
  background: rgba(240, 185, 11, 0.06);
}
.platform-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.platform-name {
  font-weight: 700;
  font-size: 14px;
}
.platform-desc {
  font-size: 12px;
  opacity: 0.7;
  line-height: 1.5;
  flex: 1;
}
.result-desc {
  font-size: 12px;
  opacity: 0.75;
  word-break: break-all;
}
.preview-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  padding: 6px 10px;
  margin-top: 6px;
  border-radius: 4px;
  background: rgba(128, 128, 128, 0.06);
  font-size: 13px;
  word-break: break-all;
}
</style>
