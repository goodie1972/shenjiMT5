<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { apiFetch } from '@/api/client'

const { t, locale } = useI18n()
const message = useMessage()
const MAX_CHARS = 2000

// 双语人设：zh ↔ soul.md/memory.md，en ↔ soul_en.md/memory_en.md
const soul = ref('')
const memory = ref('')
const soulEn = ref('')
const memoryEn = ref('')
const saving = ref(false)

const isEn = computed(() => locale.value === 'en-US')

// 当前语言的激活编辑对象（textarea 绑定）
const activeSoul = computed({
  get: () => (isEn.value ? soulEn.value : soul.value),
  set: (v: string) => { isEn.value ? (soulEn.value = v) : (soul.value = v) },
})
const activeMemory = computed({
  get: () => (isEn.value ? memoryEn.value : memory.value),
  set: (v: string) => { isEn.value ? (memoryEn.value = v) : (memory.value = v) },
})

const soulCount = computed(() => activeSoul.value.length)
const memoryCount = computed(() => activeMemory.value.length)
const soulOver = computed(() => soulCount.value > MAX_CHARS)
const memoryOver = computed(() => memoryCount.value > MAX_CHARS)
const canSave = computed(() => !soulOver.value && !memoryOver.value && !saving.value)

function countClass(count: number) {
  if (count > MAX_CHARS) return 'count-error'
  if (count >= MAX_CHARS * 0.9) return 'count-warn'
  return 'count-normal'
}

async function loadPersona() {
  try {
    const r = await apiFetch('/api/ai/persona')
    const d = await r.json()
    soul.value = d.soul || ''
    memory.value = d.memory || ''
    soulEn.value = d.soul_en || ''
    memoryEn.value = d.memory_en || ''
  } catch (e) { /* ignore */ }
}

async function savePersona() {
  if (!canSave.value) return
  saving.value = true
  try {
    const r = await apiFetch('/api/ai/persona', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      // 双语一起提交：仅当英文字段有实际内容时后端才落盘英文文件，
      // 空串不落盘 → 读取端自动镜像中文版，避免旧客户端把英文文件清空
      body: JSON.stringify({
        soul: soul.value,
        memory: memory.value,
        soul_en: soulEn.value,
        memory_en: memoryEn.value,
      }),
    })
    const d = await r.json().catch(() => ({}))
    if (!r.ok || d.error || d.detail) {
      message.error(d.error || d.detail || `${t('ai.save_failed')} (${r.status})`)
      return
    }
    message.success(t('ai.persona_saved'))
  } catch (e: any) {
    message.error(`${t('ai.save_failed')}: ${e?.message || e}`)
  } finally {
    saving.value = false
  }
}

// ── 导出：下载 soul.md / memory.md ──────────────────────
function downloadFile(filename: string, text: string) {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
function exportFiles() {
  // 导出当前语言激活的一对文件（英文环境导出英文版）
  if (isEn.value) {
    downloadFile('soul_en.md', soulEn.value)
    downloadFile('memory_en.md', memoryEn.value)
  } else {
    downloadFile('soul.md', soul.value)
    downloadFile('memory.md', memory.value)
  }
  message.success(t('ai.persona_exported'))
}

// ── 导入：选择 .md 文件读取文本 ─────────────────────────
const fileInput = ref<HTMLInputElement>()
function importFiles() {
  fileInput.value?.click()
}
function onFilesSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (!files.length) return
  let handled = 0
  for (const file of files) {
    const name = file.name.toLowerCase()
    const target = name.includes('soul') ? 'soul' : name.includes('memory') ? 'memory' : null
    if (!target) continue
    const reader = new FileReader()
    reader.onload = () => {
      const text = String(reader.result ?? '')
      if (text.length > MAX_CHARS) {
        message.warning(t('ai.persona_import_too_long', { name: file.name, count: text.length, max: MAX_CHARS }))
      }
    if (target === 'soul') isEn.value ? (soulEn.value = text) : (soul.value = text)
    else isEn.value ? (memoryEn.value = text) : (memory.value = text)
      message.success(t('ai.persona_imported', { name: file.name }))
    }
    reader.readAsText(file, 'utf-8')
    handled++
  }
  if (!handled) message.warning(t('ai.persona_import_pick_hint'))
  input.value = ''
}

onMounted(loadPersona)
</script>

<template>
  <n-card size="small" :bordered="true">
    <template #header>
      <span>{{ t('ai.persona_title') }}</span>
    </template>
    <n-space vertical :size="14">
      <!-- 基础设定 Soul -->
      <div class="persona-block">
        <div class="block-header">
          <span class="block-title">{{ t('ai.persona_soul_title') }}</span>
          <span class="char-count" :class="countClass(soulCount)">{{ soulCount }} / {{ MAX_CHARS }}</span>
        </div>
        <n-input
          v-model:value="activeSoul"
          type="textarea"
          :placeholder="t('ai.persona_soul_placeholder')"
          :rows="10"
          :maxlength="MAX_CHARS + 100"
          :status="soulOver ? 'error' : undefined"
        />
        <div v-if="soulOver" class="limit-warning">{{ t('ai.persona_soul_limit_warn', { max: MAX_CHARS }) }}</div>
      </div>

      <!-- 日常记忆 Memory -->
      <div class="persona-block">
        <div class="block-header">
          <span class="block-title">{{ t('ai.persona_memory_title') }}</span>
          <span class="char-count" :class="countClass(memoryCount)">{{ memoryCount }} / {{ MAX_CHARS }}</span>
        </div>
        <n-input
          v-model:value="activeMemory"
          type="textarea"
          :placeholder="t('ai.persona_memory_placeholder')"
          :rows="6"
          :maxlength="MAX_CHARS + 100"
          :status="memoryOver ? 'error' : undefined"
        />
        <div v-if="memoryOver" class="limit-warning">{{ t('ai.persona_memory_limit_warn', { max: MAX_CHARS }) }}</div>
      </div>

      <n-space>
        <n-button size="small" type="primary" color="#f0b90b" style="color:#1e2329" :disabled="!canSave" :loading="saving" @click="savePersona">
          {{ t('ai.persona_save') }}
        </n-button>
        <n-button size="small" @click="exportFiles">{{ t('ai.persona_export') }}</n-button>
        <n-button size="small" @click="importFiles">{{ t('ai.persona_import') }}</n-button>
        <input
          ref="fileInput"
          type="file"
          accept=".md,.markdown,text/markdown,text/plain"
          multiple
          style="display:none"
          @change="onFilesSelected"
        />
      </n-space>
    </n-space>
  </n-card>
</template>

<style scoped>
.persona-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.block-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.block-title {
  font-weight: 600;
  font-size: 13px;
  color: #f0b90b;
}
.char-count {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.count-normal {
  color: rgba(255, 255, 255, 0.45);
}
.count-warn {
  color: #f2a33c;
  font-weight: 600;
}
.count-error {
  color: #e8808a;
  font-weight: 700;
}
.limit-warning {
  font-size: 12px;
  color: #e8808a;
}
</style>
