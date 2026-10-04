<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { apiFetch } from '@/api/client'

const { t } = useI18n()
const message = useMessage()

const providers = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const fetching = ref(false)          // 「获取模型」请求中
const fetchError = ref('')           // 获取模型失败的错误信息（空=无错误）
const editingId = ref<string | null>(null)  // null=无编辑, 'new'=新增, 其他=编辑某卡片
const showModal = ref(false)  // 编辑 Modal
const showKey = ref(false)

const form = ref({
  name: '',
  type: 'openai',
  api_key: '',
  base_url: 'https://api.openai.com/v1',
  models: [] as string[],          // 服务商返回的全量模型列表
  enabled_models: [] as string[],  // 勾选要添加的模型（多选）
  selected_model: '',              // 默认使用的模型（单选，须属于 enabled_models）
})

const isEditingExisting = computed(() => editingId.value !== null && editingId.value !== 'new')

// 类型下拉选项（i18n）
const typeOptions = computed(() => [
  { label: t('ai.openai_compatible'), value: 'openai' },
  { label: t('ai.local_model'), value: 'ollama' },
])

// 勾选集合变化时，保持默认模型始终属于已勾选模型
watch(() => form.value.enabled_models, (list) => {
  if (!list.includes(form.value.selected_model)) {
    form.value.selected_model = list[0] || ''
  }
})

async function loadProviders() {
  loading.value = true
  try {
    const res = await apiFetch('/api/llm/providers')
    const d = await res.json()
    if (d.success) providers.value = d.data
  } catch (e) {
    console.error('load failed', e)
  } finally {
    loading.value = false
  }
}

function openNew() {
  editingId.value = 'new'
  showKey.value = false
  fetchError.value = ''
  showModal.value = true
  form.value = { name: '', type: 'openai', api_key: '', base_url: 'https://api.openai.com/v1', models: [], enabled_models: [], selected_model: '' }
}

function openEdit(id: string) {
  const p = providers.value.find(x => x.id === id)
  if (!p) return
  editingId.value = id
  showKey.value = false
  fetchError.value = ''
  showModal.value = true
  form.value = {
    name: p.name, type: p.type,
    // 不回填掩码 Key（后端返回的是 sk-abc...xyz 形式），留空=保持不变
    api_key: '',
    base_url: p.base_url, models: p.models || [],
    enabled_models: p.enabled_models || [],
    selected_model: p.selected_model || '',
  }
}

function cancelEdit() {
  showModal.value = false
  editingId.value = null
  showKey.value = false
  fetching.value = false
  fetchError.value = ''
}

async function saveProvider() {
  if (!form.value.name) { message.warning(t('ai.name_required')); return }
  saving.value = true
  try {
    const body: any = {
      name: form.value.name, type: form.value.type, base_url: form.value.base_url,
      models: form.value.models, enabled_models: form.value.enabled_models,
      selected_model: form.value.selected_model,
    }
    // 编辑模式下空 Key = 保持不变（不发送）；新增模式总是发送
    if (editingId.value === 'new' || form.value.api_key) {
      body.api_key = form.value.api_key
    }
    if (editingId.value === 'new') {
      const res = await apiFetch('/api/llm/providers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      const d = await res.json()
      if (!d.success) throw new Error(t('ai.save_failed', { error: JSON.stringify(d) }))
      // v4：新增成功后回读落盘核验（防止前端以为存了、实际没存）
      const newId = d.data?.id
      await loadProviders()
      const saved = newId ? providers.value.find(x => x.id === newId) : null
      if (saved && body.api_key && !saved.key_configured) {
        message.error(t('ai.save_verify_failed'))
        return
      }
      message.success(t('ai.save_verified'))
    } else {
      const res = await apiFetch(`/api/llm/providers/${editingId.value}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      const d = await res.json()
      if (!d.success) throw new Error(t('ai.save_failed', { error: JSON.stringify(d) }))
      await loadProviders()
      // v4：编辑模式下若填了新 Key，回读确认 key_configured=true
      if (form.value.api_key) {
        const saved = providers.value.find(x => x.id === editingId.value)
        if (saved && !saved.key_configured) {
          message.error(t('ai.save_verify_failed'))
          return
        }
      }
      message.success(t('ai.save_verified'))
    }
    showModal.value = false  // 关闭 Modal
    editingId.value = null
    showKey.value = false
  } catch (e: any) { message.error(t('ai.save_failed', { error: e.message || '' })) }
  finally { saving.value = false }
}

async function deleteProvider(id: string) {
  try {
    const res = await apiFetch(`/api/llm/providers/${id}`, { method: 'DELETE' })
    const d = await res.json()
    if (d.success) { message.success(t('ai.deleted')); if (editingId.value === id) editingId.value = null; await loadProviders() }
  } catch { message.error(t('ai.delete_failed')) }
}

async function activateProvider(id: string) {
  try {
    const res = await apiFetch(`/api/llm/providers/${id}/activate`, { method: 'POST' })
    const d = await res.json()
    if (d.success) { message.success(t('ai.activated')); await loadProviders() }
  } catch { message.error(t('ai.activate_failed')) }
}

// 「获取模型」：优先用表单中的 base_url/api_key；编辑已有服务商时表单 Key 不回填（空），
// 后端会按 provider_id 回退使用已保存的真实 Key（routes v3 + services v3）
// 失败时在界面显示错误原因，可点「重试」或修改输入后重新获取
async function fetchModels() {
  if (!form.value.base_url) { message.warning(t('ai.api_url_required')); return }
  if (form.value.type !== 'ollama' && !form.value.api_key && !isEditingExisting.value) { message.warning(t('ai.api_key_required')); return }
  fetching.value = true
  fetchError.value = ''
  try {
    const res = await apiFetch('/api/llm/fetch_models', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_url: form.value.base_url, api_key: form.value.api_key, type: form.value.type,
        provider_id: isEditingExisting.value ? editingId.value : '',
      }),
    })
    const d = await res.json()
    const payload = d.data || {}
    if (d.success && payload.success && payload.models?.length) {
      form.value.models = payload.models
      // 保留此前勾选中仍存在的模型；若无交集则默认全选（用户可取消勾选）
      const kept: string[] = form.value.enabled_models.filter((m: string) => payload.models.includes(m))
      form.value.enabled_models = kept.length ? kept : [...payload.models]
      message.success(t('ai.fetch_models_success', { count: payload.models.length }))
    } else {
      fetchError.value = payload.error || t('ai.fetch_models_failed')
    }
  } catch (e: any) {
    fetchError.value = e.message || t('ai.fetch_models_failed')
  } finally { fetching.value = false }
}

function checkAll() { form.value.enabled_models = [...form.value.models] }
function checkNone() { form.value.enabled_models = [] }

// 「查看已保存 Key」：列表接口只返回掩码（sk-abc...xyz），编辑已有服务商时按需
// 取回真实 Key 填入表单并自动显示（Key 属于用户本人，本地单机界面）
const revealing = ref(false)
async function revealKey() {
  if (!isEditingExisting.value) return
  revealing.value = true
  try {
    const res = await apiFetch(`/api/llm/providers/${editingId.value}/key`)
    const d = await res.json()
    if (d.success && d.data?.api_key) {
      form.value.api_key = d.data.api_key
      showKey.value = true
      message.success(t('ai.key_filled'))
    } else {
      message.warning(t('ai.key_not_found'))
    }
  } catch (e: any) {
    message.error(t('ai.key_fetch_failed', { error: e.message || '' }))
  } finally { revealing.value = false }
}

onMounted(loadProviders)
</script>

<template>
  <n-card size="small" :bordered="true">
    <template #header>
      <span>{{ t('ai.provider_title') }}</span>
    </template>
    <n-spin :show="loading" size="small">
      <div v-if="!loading && providers.length === 0" style="text-align:center;padding:60px 0;color:#8b8f97">
        {{ t('ai.no_providers') }}
      </div>

      <!-- 卡片网格：统一 .tile-grid（等宽等高，内容超出行内滚动） -->
      <div class="tile-grid" style="--tile-h:190px">
        <div v-for="p in providers" :key="p.id"
          class="tile tile-click" :class="p.is_active ? 'tile-on' : 'tile-off'"
          @click="openEdit(p.id)">
          <!-- 头部：名称 + 开关（固定） -->
          <div class="tile-hd u-row">
            <span class="u-ellipsis" :title="p.name" style="font-weight:600;font-size:15px">{{ p.name }}</span>
            <div @click.stop style="flex-shrink:0">
              <n-switch :value="p.is_active" size="small" @update:value="() => activateProvider(p.id)" :round="true" />
            </div>
          </div>
          <!-- 主体：唯一滚动区 -->
          <div class="tile-bd">
            <div class="u-break" style="font-size:13px;margin-bottom:4px">{{ p.selected_model || (p.models?.[0] || '') }}</div>
            <div class="u-break" style="font-size:12px;margin-bottom:4px">
              <span v-if="p.api_key">{{ p.api_key }}</span>
              <span v-else style="color:#e38181">{{ t('ai.smithery_key_not_configured') }}</span>
            </div>
            <div class="u-break" style="font-size:11px;color:#8b8f97">{{ p.base_url || t('ai.provider_incomplete') }}</div>
            <!-- v4：激活但未配置完整（无 key 或无 URL）→ 红色警示（消除"开关开着=有配置"的误导） -->
            <n-alert v-if="p.is_active && (!p.key_configured || !p.base_url)" type="error" size="small" style="margin-top:6px">
              <div style="font-size:11px">{{ t('ai.provider_incomplete_active') }}</div>
            </n-alert>
            <n-alert v-else-if="!p.is_active && !p.key_configured" type="warning" size="small" style="margin-top:6px">
              <div style="font-size:11px">{{ t('ai.provider_incomplete') }}</div>
            </n-alert>
          </div>
          <!-- 底部（固定） -->
          <div class="tile-ft u-row">
            <n-tag v-if="p.is_active" :bordered="false" size="tiny" type="success">{{ t('ai.activated') }}</n-tag>
            <span v-else />
            <div v-if="!p.is_active" @click.stop style="flex-shrink:0">
              <n-popconfirm @positive-click="deleteProvider(p.id)">
                <template #trigger><n-button size="tiny" quaternary type="error">✕</n-button></template>
                {{ t('ai.confirm_delete') }}
              </n-popconfirm>
            </div>
          </div>
        </div>

        <!-- 空白卡片 -->
        <div v-if="!showModal" class="tile tile-dash tile-click" @click="openNew">
          <span style="font-size:26px;color:#8b8f97;line-height:1">+</span>
          <span style="font-size:13px;color:#8b8f97">{{ t('ai.add_provider') }}</span>
        </div>
      </div>
    </n-spin>

    <!-- 编辑 Modal → 弹出放大 -->
    <n-modal v-model:show="showModal" :mask-closable="false" preset="card" style="max-width:600px" :title="editingId === 'new' ? t('ai.add_provider') : t('ai.configure')">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px">
        <div>
          <div style="font-size:12px;color:#8b8f97;margin-bottom:4px">{{ t('ai.name') }}</div>
          <n-input v-model:value="form.name" size="small" :placeholder="t('ai.name_placeholder')" />
        </div>
        <div>
          <div style="font-size:12px;color:#8b8f97;margin-bottom:4px">{{ t('ai.type') }}</div>
          <n-select v-model:value="form.type" size="small" :options="typeOptions" />
        </div>
        <div style="grid-column:span 2">
          <div style="font-size:12px;color:#8b8f97;margin-bottom:4px">{{ t('ai.base_url') }}</div>
          <n-input v-model:value="form.base_url" size="small" placeholder="https://api.openai.com/v1" />
        </div>
        <div style="grid-column:span 2">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <div style="font-size:12px;color:#8b8f97">{{ t('ai.api_key') }}</div>
            <n-button v-if="isEditingExisting" text size="tiny" type="primary" :loading="revealing" @click="revealKey">
              {{ t('ai.view_saved_key') }}
            </n-button>
          </div>
          <n-input v-model:value="form.api_key" size="small" :type="showKey ? 'text' : 'password'" :placeholder="isEditingExisting ? t('ai.keep_empty') : 'sk-...'">
            <template #suffix>
              <span @click="showKey = !showKey" style="cursor:pointer;color:#8b8f97;font-size:16px" :title="showKey ? t('ai.hide_key') : t('ai.show_key')">
                {{ showKey ? '👁️' : '🙈' }}
              </span>
            </template>
          </n-input>
        </div>
        <!-- 获取模型：无状态拉取服务商可用模型列表 -->
        <div style="grid-column:span 2">
          <n-button size="small" secondary type="primary" :loading="fetching" :disabled="!form.base_url" @click="fetchModels">
            {{ t('ai.fetch_models') }}
          </n-button>
        </div>

        <!-- 获取失败：错误提示 + 重试 -->
        <div v-if="fetchError" style="grid-column:span 2">
          <n-alert type="error" size="small" closable @close="fetchError = ''">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:12px">
              <span style="font-size:12px">{{ t('ai.fetch_models_failed') }}：{{ fetchError }}</span>
              <n-button size="tiny" type="error" secondary :loading="fetching" @click="fetchModels">
                {{ t('ai.retry') }}
              </n-button>
            </div>
          </n-alert>
        </div>

        <!-- 模型多选列表：勾选要添加的模型 -->
        <div style="grid-column:span 2">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <div style="font-size:12px;color:#8b8f97">{{ t('ai.select_models_hint') }}</div>
            <div v-if="form.models.length" style="display:flex;gap:10px;align-items:center">
              <n-button text size="tiny" type="primary" @click="checkAll">{{ t('ai.select_all') }}</n-button>
              <n-button text size="tiny" @click="checkNone">{{ t('ai.clear_selection') }}</n-button>
              <span style="font-size:11px;color:#8b8f97">{{ t('ai.selected_count', { count: form.enabled_models.length }) }}</span>
            </div>
          </div>
          <div v-if="form.models.length"
            style="max-height:180px;overflow-y:auto;border:1px solid var(--n-border-color);border-radius:6px;padding:8px 12px">
            <n-checkbox-group v-model:value="form.enabled_models">
              <div v-for="m in form.models" :key="m" style="padding:3px 0">
                <n-checkbox :value="m" size="small">
                  <span style="font-size:12px">{{ m }}</span>
                </n-checkbox>
              </div>
            </n-checkbox-group>
          </div>
          <div v-else style="font-size:12px;color:#8b8f97;padding:2px 0">
            {{ t('ai.fetch_models_hint') }}
          </div>
        </div>

        <div style="grid-column:span 2">
          <div style="font-size:12px;color:#8b8f97;margin-bottom:4px">{{ t('ai.model') }}</div>
          <n-select v-model:value="form.selected_model" size="small" filterable clearable :placeholder="t('ai.model_placeholder')"
            :options="form.enabled_models.map(m => ({ label: m, value: m }))" />
        </div>
      </div>

      <template #footer>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:11px;color:#8b8f97">{{ t('ai.keep_empty') }}</span>
          <div style="display:flex;gap:8px">
            <n-button size="small" quaternary @click="cancelEdit">{{ t('ai.cancel') }}</n-button>
            <n-button type="primary" size="small" @click="saveProvider" :loading="saving">{{ t('ai.save') }}</n-button>
          </div>
        </div>
      </template>
    </n-modal>
  </n-card>
</template>
