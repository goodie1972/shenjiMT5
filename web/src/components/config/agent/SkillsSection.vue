<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useLocaleText } from '../../../composables/useLocaleText'
import { apiFetch } from '@/api/client'

const { t, locale } = useI18n()
const { pickEn } = useLocaleText()
const message = useMessage()

// ── 技能数据 ──
const skills = ref<any[]>([])
const switchingSkill = ref<string | null>(null)
const uninstalling = ref<string | null>(null)
const rescanning = ref(false)
const LS_DISABLED_SKILLS = 'disabled_skill_meta'
const disabledSkillMeta = ref<Record<string, string>>({})

function errOf(res: any, d: any): string {
  return d?.error || d?.detail || res.statusText || `HTTP ${res.status}`
}

async function loadSkills() {
  try {
    try { disabledSkillMeta.value = JSON.parse(localStorage.getItem(LS_DISABLED_SKILLS) || '{}') }
    catch { disabledSkillMeta.value = {} }
    const r = await apiFetch('/api/ai/skills')
    const d = await r.json()
    const list = (d.skills || []).map((s: any) => {
      const item = { source: 'builtin', source_label: t('ai.skill.source_builtin'), ...s }
      // 后端 source_label 为中文 → 前端按来源重映射为当前语言文案
      if (item.source === 'builtin') item.source_label = t('ai.skill.source_builtin')
      else if (item.source === 'local') item.source_label = t('ai.skill.source_local')
      else if (item.source === 'paste') item.source_label = t('ai.skill.paste_import')
      else if (item.source === 'unknown') item.source_label = t('ai.skill.source_unknown')
      return item
    })
    const names = new Set(list.map((s: any) => s.name))
    const extra = Object.entries(disabledSkillMeta.value)
      .filter(([name]) => !names.has(name))
      .map(([name, description]) => ({ name, description, enabled: false, source: 'unknown', source_label: t('ai.skill.source_unknown') }))
    skills.value = [...list, ...extra]
  } catch { /* ignore */ }
}

async function toggleSkill(skill: any, enabled: boolean) {
  switchingSkill.value = skill.name
  try {
    const res = await apiFetch(`/api/ai/skills/${encodeURIComponent(skill.name)}/${enabled ? 'enable' : 'disable'}`, { method: 'PUT' })
    let d: any = {}
    try { d = await res.json() } catch { /* ignore */ }
    if (!res.ok || !d.ok) {
      message.error(t('ai.skill.toggle_failed', { error: errOf(res, d) }))
      await loadSkills()
      return
    }
    skill.enabled = enabled
    if (enabled) delete disabledSkillMeta.value[skill.name]
    else disabledSkillMeta.value[skill.name] = skill.description || ''
    localStorage.setItem(LS_DISABLED_SKILLS, JSON.stringify(disabledSkillMeta.value))
    message.success(enabled ? t('ai.skill.enabled_msg', { name: skill.name }) : t('ai.skill.disabled_msg', { name: skill.name }))
  } catch { message.error(t('ai.skill.toggle_failed', { error: '' })) }
  finally { switchingSkill.value = null }
}

async function uninstallSkill(name: string) {
  uninstalling.value = name
  try {
    const res = await apiFetch(`/api/ai/skill-store/${encodeURIComponent(name)}`, { method: 'DELETE' })
    let d: any = {}
    try { d = await res.json() } catch { /* ignore */ }
    if (!res.ok || d.ok === false) {
      message.error(t('ai.skill.uninstall_failed', { error: errOf(res, d) }))
      return
    }
    delete disabledSkillMeta.value[name]
    localStorage.setItem(LS_DISABLED_SKILLS, JSON.stringify(disabledSkillMeta.value))
    message.success(t('ai.skill.uninstalled', { name }))
    await loadSkills()
  } catch { message.error(t('ai.skill.uninstall_failed', { error: '' })) }
  finally { uninstalling.value = null }
}

async function rescanSkills() {
  rescanning.value = true
  try {
    const res = await apiFetch('/api/ai/skills/rescan', { method: 'POST' })
    const d = await res.json()
    if (res.ok) message.success(t('ai.skill.rescanned', { count: d.skill_count ?? 0 }))
    else message.error(t('ai.skill.rescan_failed', { error: errOf(res, d) }))
    await loadSkills()
  } catch { message.error(t('ai.skill.rescan_failed', { error: '' })) }
  finally { rescanning.value = false }
}

// ── 来源标签 ──
function sourceTagType(s: any): 'warning' | 'info' | 'success' | 'default' {
  if (s.source === 'builtin') return 'warning'
  if (s.source === 'local') return 'info'
  if (['skillsh', 'clawhub', 'skillsmp', 'skillhubcn', 'paste'].includes(s.source)) return 'success'
  return 'default'
}

// ── 图标色块（首字母 + 来源色）──
function iconBg(s: any): string {
  if (s.source === 'builtin') return '#f0b90b'
  if (s.source === 'local') return '#36ad6a'
  if (['skillsh', 'clawhub', 'skillsmp', 'skillhubcn', 'paste'].includes(s.source)) return '#18a058'
  return '#909399'
}
function iconLetter(s: any): string {
  return (s.name || '?')[0].toUpperCase()
}

// 启用数
const enabledCount = computed(() => skills.value.filter((s: any) => s.enabled).length)

// ════════════════════════════════════════════
// 本地添加 — 目录浏览器
// ════════════════════════════════════════════
const showLocalModal = ref(false)
const browsePath = ref('')          // 当前浏览路径
const browseParent = ref('')        // 父路径
const browseDirs = ref<any[]>([])   // 子目录列表
const browsing = ref(false)
const selectedDir = ref('')         // 选中的目录路径
const validating = ref(false)
const validationResult = ref<any | null>(null)  // {valid, count, skills:[]}
const registering = ref(false)
// 已注册目录
const localDirs = ref<string[]>([])
const removingDir = ref('')

async function openLocalModal() {
  showLocalModal.value = true
  validationResult.value = null
  selectedDir.value = ''
  await Promise.all([browseTo(''), loadLocalDirs()])
}

async function loadLocalDirs() {
  try {
    const r = await apiFetch('/api/ai/skills/local-dirs')
    const d = await r.json()
    localDirs.value = d.dirs || []
  } catch { /* ignore */ }
}

async function browseTo(path: string) {
  browsing.value = true
  try {
    const r = await apiFetch(`/api/ai/skills/browse-dirs?path=${encodeURIComponent(path)}`)
    const d = await r.json()
    if (d.error) { message.error(d.error); return }
    browsePath.value = d.path
    browseParent.value = d.parent
    browseDirs.value = d.dirs || []
    selectedDir.value = ''
    validationResult.value = null
  } catch { message.error(t('ai.skill.browse_failed')) }
  finally { browsing.value = false }
}

async function selectDir(dirPath: string) {
  selectedDir.value = dirPath
  validationResult.value = null
}

async function validateSelected() {
  if (!selectedDir.value) { message.warning(t('ai.skill.select_dir_first')); return }
  validating.value = true
  try {
    const res = await apiFetch('/api/ai/skills/validate-dir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: selectedDir.value }),
    })
    let d: any = {}
    try { d = await res.json() } catch { /* ignore */ }
    if (!res.ok) { message.error(t('ai.skill.validate_failed', { error: errOf(res, d) })); return }
    validationResult.value = d
    if (!d.valid) message.warning(t('ai.skill.no_skill_md_warning'))
  } catch { message.error(t('ai.skill.validate_failed', { error: '' })) }
  finally { validating.value = false }
}

async function registerSelected() {
  if (!selectedDir.value) { message.warning(t('ai.skill.select_dir_first')); return }
  registering.value = true
  try {
    const res = await apiFetch('/api/ai/skills/local-dir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: selectedDir.value }),
    })
    let d: any = {}
    try { d = await res.json() } catch { /* ignore */ }
    if (!res.ok || d.ok === false) { message.error(t('ai.skill.register_failed', { error: errOf(res, d) })); return }
    message.success(t('ai.skill.registered', { count: d.skill_count ?? 0 }))
    showLocalModal.value = false
    await Promise.all([loadLocalDirs(), loadSkills()])
  } catch { message.error(t('ai.skill.register_failed', { error: '' })) }
  finally { registering.value = false }
}

async function removeDir(path: string) {
  removingDir.value = path
  try {
    const res = await apiFetch('/api/ai/skills/local-dir', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    })
    let d: any = {}
    try { d = await res.json() } catch { /* ignore */ }
    if (!res.ok) { message.error(t('ai.skill.remove_failed', { error: errOf(res, d) })); return }
    message.success(t('ai.skill.removed'))
    await Promise.all([loadLocalDirs(), loadSkills()])
  } catch { message.error(t('ai.skill.remove_failed', { error: '' })) }
  finally { removingDir.value = '' }
}

// ════════════════════════════════════════════
// 商店添加 — 平台列表 + 搜索 + 安装确认
// ════════════════════════════════════════════
const showStoreModal = ref(false)
const platforms = ref<any[]>([])
const selectedPlatform = ref('skillsh')
const loadingPlatforms = ref(false)

const searchQuery = ref('')
const searching = ref(false)
const searchResults = ref<any[]>([])
const searchError = ref('')
const searchDone = ref(false)
const installingRef = ref('')

// 安装确认弹窗
const showConfirm = ref(false)
const confirmItem = ref<any | null>(null)
const confirming = ref(false)

// 粘贴区
const pasteText = ref('')
const installingPaste = ref(false)

// 平台等级标签文案
function storeLevelLabel(p: any): string {
  if (p.level === 'api') return t('ai.skill.store_level_api')
  if (p.level === 'template') return t('ai.skill.store_level_template')
  return t('ai.skill.store_level_browse')
}

const currentPlatform = computed(() =>
  platforms.value.find((p: any) => p.id === selectedPlatform.value))

async function openStoreModal() {
  showStoreModal.value = true
  searchError.value = ''
  if (!platforms.value.length) {
    loadingPlatforms.value = true
    try {
      const r = await apiFetch('/api/ai/skill-store/platforms')
      const d = await r.json()
      platforms.value = d.platforms || []
    } catch { message.error(t('ai.skill.platforms_load_failed')) }
    finally { loadingPlatforms.value = false }
  }
}

function openPlatform(url: string) {
  window.open(url, '_blank')
}

async function doSearch() {
  const q = searchQuery.value.trim()
  if (!q) { message.warning(t('ai.skill.search_required')); return }
  searching.value = true
  searchError.value = ''
  searchResults.value = []
  searchDone.value = false
  try {
    // v2：按当前选中平台搜索（新增 ClawHub 后不能再写死 skillsh）
    const res = await apiFetch(`/api/ai/skill-store/search?platform=${encodeURIComponent(selectedPlatform.value)}&q=${encodeURIComponent(q)}`)
    let d: any = {}
    try { d = await res.json() } catch { /* ignore */ }
    if (!res.ok) { searchError.value = errOf(res, d); return }
    searchResults.value = d.results || []
    searchDone.value = true
  } catch { searchError.value = t('ai.skill.search_error') }
  finally { searching.value = false }
}

// 点"安装"→ 弹出确认（而非直接装）
function askInstall(item: any) {
  confirmItem.value = item
  showConfirm.value = true
}

async function confirmInstall() {
  if (!confirmItem.value) return
  confirming.value = true
  try {
    const item = confirmItem.value
    const res = await apiFetch('/api/ai/skill-store/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ platform: selectedPlatform.value, ref: item.ref || item.name, locale: locale.value }),
    })
    let d: any = {}
    try { d = await res.json() } catch { /* ignore */ }
    if (!res.ok || d.ok === false) { message.error(t('ai.skill.install_failed', { error: errOf(res, d) })); return }
    message.success(t('ai.skill.installed', { name: d.name }))
    showConfirm.value = false
    confirmItem.value = null
    await loadSkills()
  } catch { message.error(t('ai.skill.install_failed', { error: '' })) }
  finally { confirming.value = false }
}

async function askInstallPaste() {
  const text = pasteText.value.trim()
  if (!text) { message.warning(t('ai.skill.paste_required')); return }
  // 粘贴内容直接走确认流程
  const isContent = text.startsWith('---')
  confirmItem.value = {
    name: isContent ? t('ai.skill.paste_import') : text.slice(0, 40),
    description: isContent ? t('ai.skill.paste_content') : t('ai.skill.paste_link'),
    _isPaste: true,
  }
  showConfirm.value = true
}

async function confirmPasteInstall() {
  if (!confirmItem.value) return
  confirming.value = true
  try {
    const text = pasteText.value.trim()
    const isContent = text.startsWith('---')
    const body = isContent
      ? { platform: selectedPlatform.value, content: text, locale: locale.value }
      : { platform: selectedPlatform.value, ref: text, locale: locale.value }
    const res = await apiFetch('/api/ai/skill-store/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    let d: any = {}
    try { d = await res.json() } catch { /* ignore */ }
    if (!res.ok || d.ok === false) { message.error(t('ai.skill.install_failed', { error: errOf(res, d) })); return }
    message.success(t('ai.skill.installed', { name: d.name }))
    pasteText.value = ''
    showConfirm.value = false
    confirmItem.value = null
    await loadSkills()
  } catch { message.error(t('ai.skill.install_failed', { error: '' })) }
  finally { confirming.value = false }
}

onMounted(loadSkills)
</script>

<template>
  <n-card size="small" :bordered="true">
    <template #header>
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <span>{{ t('ai.skill.header', { total: skills.length, enabled: enabledCount }) }}</span>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
          <n-button size="tiny" quaternary :loading="rescanning" @click="rescanSkills">{{ t('ai.skill.rescan') }}</n-button>
          <n-button size="tiny" secondary type="success" @click="openStoreModal">{{ t('ai.skill.add_from_store') }}</n-button>
          <n-button size="tiny" secondary type="info" @click="openLocalModal">{{ t('ai.skill.add_local') }}</n-button>
        </div>
      </div>
    </template>

    <n-spin :show="false">
      <!-- ── 技能卡片网格 ── -->
      <div v-if="skills.length > 0" class="tile-grid" style="--tile-h:190px">
        <div v-for="s in skills" :key="s.name"
          class="tile"
          :class="s.enabled ? 'tile-on' : 'tile-off'"
          :style="{ borderLeftColor: iconBg(s), borderLeftWidth: '3px' }">
          <!-- 头部：图标 + 名称（固定） -->
          <div class="tile-hd card-top">
            <div class="skill-icon" :style="{ background: iconBg(s) }">{{ iconLetter(s) }}</div>
            <div class="skill-meta">
              <div class="skill-name u-ellipsis" :title="s.name">{{ s.name }}</div>
              <div class="skill-tags">
                <n-tag size="tiny" :bordered="false" :type="sourceTagType(s)">
                  {{ s.source_label || s.source }}
                </n-tag>
              </div>
            </div>
          </div>
          <!-- 主体：描述（唯一滚动区，完整显示不再截断） -->
          <div class="tile-bd">
            <div class="u-break" style="font-size:12px;opacity:0.7;line-height:1.45">
              {{ pickEn(s) || t('ai.skill.no_desc') }}
            </div>
          </div>
          <!-- 底部操作（固定） -->
          <div class="tile-ft card-bottom">
            <n-switch :value="!!s.enabled" size="small" :loading="switchingSkill === s.name"
              @update:value="(v: boolean) => toggleSkill(s, v)" />
            <n-popconfirm v-if="s.source !== 'builtin'"
              @positive-click="uninstallSkill(s.name)"
              :positive-text="t('ai.skill.uninstall')" :negative-text="t('ai.cancel')">
              <template #trigger>
                <n-button size="tiny" quaternary type="error"
                  :loading="uninstalling === s.name">{{ t('ai.skill.uninstall') }}</n-button>
              </template>
              {{ t('ai.skill.confirm_uninstall', { name: s.name }) }}
            </n-popconfirm>
          </div>
        </div>
      </div>
      <n-empty v-else :description="t('ai.skill.no_skills')" style="padding:24px" />
    </n-spin>

    <!-- ══ 本地添加 Modal — 目录浏览器 ══ -->
    <n-modal v-model:show="showLocalModal" preset="card" :title="t('ai.skill.local_modal_title')"
      style="width: 680px; max-width: 94vw">
      <!-- ① 目录浏览器 -->
      <div style="font-size:13px;font-weight:600;margin-bottom:8px">{{ t('ai.skill.step1') }}</div>
      <!-- 当前路径 + 返回上级 -->
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
        <n-button size="small" quaternary :disabled="!browseParent || browsing"
          @click="browseTo(browseParent)">{{ t('ai.skill.up') }}</n-button>
        <n-ellipsis style="flex:1;font-size:12px;font-family:var(--font-mono);opacity:0.8" :tooltip="true">
          {{ browsePath || t('ai.skill.loading') }}
        </n-ellipsis>
        <n-button size="small" quaternary :loading="browsing" @click="browseTo(browsePath)">{{ t('common.refresh') }}</n-button>
      </div>
      <!-- 子目录列表 -->
      <n-spin :show="browsing">
        <div class="dir-list">
          <div v-for="d in browseDirs" :key="d.path"
            class="dir-item"
            :class="{ selected: selectedDir === d.path, 'has-skill': d.has_skill }"
            @click="selectDir(d.path)"
            @dblclick="browseTo(d.path)">
            <span style="font-size:14px">📁</span>
            <span class="dir-name" :title="d.name">{{ d.name }}</span>
            <n-tag v-if="d.has_skill" size="tiny" :bordered="false" type="success" style="margin-left:auto">
              {{ t('ai.skill.has_skill') }}
            </n-tag>
          </div>
          <n-empty v-if="!browsing && browseDirs.length === 0" size="small" :description="t('ai.skill.no_subdir')" />
        </div>
      </n-spin>
      <div style="font-size:11px;opacity:0.5;margin-top:6px">{{ t('ai.skill.single_click_hint') }}</div>

      <!-- ② 验证结果 -->
      <div v-if="selectedDir" style="margin-top:14px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <span style="font-size:13px;font-weight:600">{{ t('ai.skill.step2') }}</span>
          <n-button size="small" type="primary" secondary :loading="validating" @click="validateSelected">{{ t('ai.skill.validate') }}</n-button>
        </div>
        <div v-if="validationResult" class="validate-result">
          <n-tag v-if="validationResult.valid" size="small" :bordered="false" type="success">
            {{ t('ai.skill.found_skills', { count: validationResult.count }) }}
          </n-tag>
          <n-tag v-else size="small" :bordered="false" type="warning">{{ t('ai.skill.no_skill_md') }}</n-tag>
          <div v-if="validationResult.skills?.length" style="margin-top:6px">
            <div v-for="sk in validationResult.skills" :key="sk.name" class="validate-skill">
              <span style="font-weight:500">{{ sk.name }}</span>
              <span style="opacity:0.6;margin-left:8px;font-size:12px">{{ pickEn(sk) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ③ 注册 -->
      <div style="margin-top:14px;display:flex;justify-content:flex-end;gap:8px">
        <n-button size="small" quaternary @click="showLocalModal = false">{{ t('ai.cancel') }}</n-button>
        <n-button size="small" type="primary" :loading="registering"
          :disabled="!selectedDir" @click="registerSelected">{{ t('ai.skill.register') }}</n-button>
      </div>

      <n-divider style="margin:14px 0" />

      <!-- 已注册目录 -->
      <div style="font-size:13px;font-weight:600;margin-bottom:8px">{{ t('ai.skill.registered_dirs') }}</div>
      <div v-if="localDirs.length > 0" style="display:flex;flex-direction:column;gap:6px">
        <div v-for="dir in localDirs" :key="dir" class="local-dir-row">
          <n-ellipsis style="flex:1;font-size:12px;font-family:var(--font-mono)" :tooltip="true">{{ dir }}</n-ellipsis>
          <n-button size="tiny" quaternary type="error"
            :loading="removingDir === dir" @click="removeDir(dir)">{{ t('ai.skill.remove') }}</n-button>
        </div>
      </div>
      <n-text v-else depth="3" style="font-size:12px">{{ t('ai.skill.no_registered') }}</n-text>
    </n-modal>

    <!-- ══ 商店 Modal ══ -->
    <n-modal v-model:show="showStoreModal" preset="card" :title="t('ai.skill.store_modal_title')"
      style="width: 720px; max-width: 94vw">
      <!-- 平台列表 -->
      <n-spin :show="loadingPlatforms">
        <div class="platform-grid">
          <div v-for="p in platforms" :key="p.id"
            class="platform-card" :class="{ active: selectedPlatform === p.id }"
            @click="selectedPlatform = p.id">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:6px">
              <span style="font-weight:700;font-size:14px">{{ pickEn(p, 'name') }}</span>
              <n-tag size="tiny" :bordered="false" :type="p.level === 'api' ? 'success' : 'default'">
                {{ p.grade }} {{ t('ai.grade_unit') }} · {{ storeLevelLabel(p) }}
              </n-tag>
            </div>
            <div class="tile-bd" style="font-size:12px;opacity:0.7;line-height:1.5">{{ pickEn(p) }}</div>
            <n-button size="tiny" quaternary @click.stop="openPlatform(p.url)">{{ t('ai.mcp.open_platform') }}</n-button>
          </div>
        </div>
      </n-spin>

      <n-divider style="margin:14px 0" />

      <!-- A 级平台（skill.sh / ClawHub）：系统内搜索 -->
      <div v-if="currentPlatform?.level === 'api'">
        <n-input-group>
          <n-input v-model:value="searchQuery" :placeholder="t('ai.skill.search_in', { name: pickEn(currentPlatform, 'name') })"
            clearable @keydown.enter="doSearch" />
          <n-button type="primary" :loading="searching" @click="doSearch">{{ t('ai.skill.search') }}</n-button>
        </n-input-group>
        <div style="margin-top:12px">
          <n-spin :show="searching">
            <n-alert v-if="searchError" type="warning" :bordered="false" style="margin-bottom:8px">
              {{ searchError }}
            </n-alert>
            <n-empty v-else-if="searchDone && searchResults.length === 0" size="small" :description="t('ai.skill.no_results')" />
            <div v-if="searchResults.length > 0" class="search-results">
              <div v-for="item in searchResults" :key="item.ref || item.name" class="search-item">
                <div style="flex:1;min-width:0">
                  <div style="font-weight:600;font-size:13px">{{ item.name }}</div>
                  <div style="font-size:12px;opacity:0.7;margin-top:2px;word-break:break-all">
                    {{ pickEn(item) || item.ref }}
                  </div>
                </div>
                <n-button size="tiny" type="primary" secondary @click="askInstall(item)">{{ t('ai.skill.install') }}</n-button>
              </div>
            </div>
          </n-spin>
        </div>
      </div>

      <!-- C 级平台（skillsmp / skillhub.cn）：粘贴区 -->
      <div v-else>
        <n-alert type="info" :bordered="false" style="margin-bottom:8px">
          {{ t('ai.skill.c_level_hint', { name: pickEn(currentPlatform, 'name') }) }}
        </n-alert>
        <n-input v-model:value="pasteText" type="textarea" :rows="6"
          :placeholder="t('ai.skill.paste_hint')" />
        <div style="margin-top:10px;text-align:right">
          <n-button type="primary" size="small" @click="askInstallPaste">{{ t('ai.skill.identify_install') }}</n-button>
        </div>
      </div>
    </n-modal>

    <!-- ══ 安装确认弹窗 ══ -->
    <n-modal v-model:show="showConfirm" preset="card" :title="t('ai.skill.confirm_title')"
      style="width: 460px; max-width: 92vw">
      <div v-if="confirmItem" style="padding:4px 0">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
          <div class="skill-icon" style="background:#18a058">
            {{ (confirmItem.name || '?')[0].toUpperCase() }}
          </div>
          <div>
            <div style="font-weight:600;font-size:15px">{{ confirmItem.name }}</div>
            <n-tag size="tiny" :bordered="false" type="success">
              {{ confirmItem._isPaste ? t('ai.skill.paste_import') : 'skill.sh' }}
            </n-tag>
          </div>
        </div>
        <div style="font-size:13px;opacity:0.8;line-height:1.6;margin-bottom:12px">
          {{ pickEn(confirmItem) || t('ai.skill.no_desc') }}
        </div>
        <n-alert type="info" :bordered="false" style="margin-bottom:8px">
          {{ t('ai.skill.confirm_default_disabled') }}
        </n-alert>
        <n-alert v-if="!confirmItem._isPaste" type="warning" :bordered="false">
          {{ t('ai.skill.confirm_remote_warning') }}
        </n-alert>
      </div>
      <template #footer>
        <div style="display:flex;justify-content:flex-end;gap:8px">
          <n-button size="small" quaternary @click="showConfirm = false; confirmItem = null">{{ t('ai.cancel') }}</n-button>
          <n-button size="small" type="primary" :loading="confirming"
            @click="confirmItem?._isPaste ? confirmPasteInstall() : confirmInstall()">
            {{ t('ai.skill.confirm_install') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </n-card>
</template>

<style scoped>
/* 网格与卡片骨架统一走全局 src/styles/tile.css（.tile-grid / .tile / .tile-hd /
   .tile-bd / .tile-ft）——等宽等高 + 内容超出卡片内滚动。此处只保留技能专属样式。 */
.card-top {
  display: flex;
  align-items: center;
  gap: 10px;
}
.skill-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 16px;
  color: #fff;
  flex-shrink: 0;
}
.skill-meta {
  flex: 1;
  min-width: 0;
}
.skill-name {
  font-weight: 600;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.skill-tags {
  margin-top: 2px;
}
.card-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  margin-top: auto;
}

/* ── 目录浏览器 ── */
.dir-list {
  max-height: 280px;
  overflow-y: auto;
  border: 1px solid var(--n-border-color, rgba(128,128,128,0.2));
  border-radius: 8px;
  padding: 4px;
}
.dir-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  font-size: 13px;
}
.dir-item:hover {
  background: rgba(128,128,128,0.08);
}
.dir-item.selected {
  background: rgba(54,173,106,0.12);
  border: 1px solid rgba(54,173,106,0.4);
}
.dir-item.has-skill .dir-name {
  font-weight: 600;
}
.dir-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.validate-result {
  padding: 10px 12px;
  border: 1px solid var(--n-border-color, rgba(128,128,128,0.2));
  border-radius: 8px;
  background: rgba(128,128,128,0.04);
}
.validate-skill {
  padding: 3px 0;
  font-size: 13px;
  border-bottom: 1px dashed rgba(128,128,128,0.15);
}
.validate-skill:last-child {
  border-bottom: none;
}
.local-dir-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  border: 1px solid rgba(128,128,128,0.2);
  border-radius: 6px;
}

/* ── 平台卡片（统一卡片契约：minmax(240px,1fr) + 固定行高 + overflow 不外溢）── */
.platform-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  grid-auto-rows: 132px;   /* 固定行高 → 平台卡片等高，描述超出内部滚动 */
  gap: 10px;
}
.platform-card {
  border: 1px solid rgba(128,128,128,0.25);
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  display: flex;
  flex-direction: column;
  gap: 6px;
  height: 100%;
  overflow: hidden;        /* 不外溢遮挡 */
}
.platform-card:hover {
  border-color: rgba(24,160,88,0.6);
}
.platform-card.active {
  border-color: #18a058;
  background: rgba(24,160,88,0.06);
}

/* ── 搜索结果 ── */
.search-results {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.search-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid rgba(128,128,128,0.2);
  border-radius: 8px;
}
</style>
