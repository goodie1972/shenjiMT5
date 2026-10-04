<script setup lang="ts">
/**
 * BacktestPanel.vue — v12 重构
 *
 * 操作流程：选择策略 → 选择数据源 → 配置资金/手续费/滑点/杠杆
 * - 策略单选，选定后周期自动锁定
 * - 数据源选定后展示品种+起始时间
 * - 四个配置项排列同一行，上下选择器宽度紧凑
 */
import { ref, computed, onMounted, onUnmounted, h, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useBacktestStore } from '@/stores/backtest'
import { useMessage, useDialog } from 'naive-ui'
import {
  fetchExternalData,
  getExternalDataStatus,
  getExternalDataCoverage,
  getKlineRange,
} from '@/api/client'
import type { ExternalDataCoverage, KlineRangeInfo } from '@/types'

const { t } = useI18n()
const backtest = useBacktestStore()
const message = useMessage()
const dialog = useDialog()

/** A=现有策略 B=组合指标 C=公式策略 */
const mode = ref<'live' | 'combo' | 'formula'>('live')

// ---------- 策略单选 ----------
/** 当前选中的策略名（单选） */
const selectedStrategy = ref<string | null>(null)

/** 策略选项（不按周期分组，直接列出全部，展示各自的周期标签） */
const strategySelectOptions = computed(() => {
  const real = backtest.realStrategies.map(s => ({
    label: s.timeframe ? `${s.name} (${s.timeframe})` : s.name,
    value: s.name,
  }))
  const builtin = backtest.builtinStrategies.map(s => ({
    label: s.name,
    value: s.name,
  }))
  return [
    { type: 'group' as const, label: '实盘策略', key: 'real', children: real },
    { type: 'group' as const, label: '内置策略', key: 'builtin', children: builtin },
  ]
})

/** 选定策略后自动确定的周期 */
const strategyTimeframe = computed(() => {
  if (!selectedStrategy.value) return null
  const s = backtest.realStrategies.find(s => s.name === selectedStrategy.value)
  return s?.timeframe || null
})

/** 周期是否锁定（选了策略后即锁定） */
const timeframeLocked = computed(() => !!selectedStrategy.value && !!strategyTimeframe.value)

const timeframeOptions = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1'].map(v => ({ label: v, value: v }))

/** 策略选择变化（单选） */
function onStrategySelect(val: string | null) {
  selectedStrategy.value = val
  if (val) {
    // 自动设置周期
    const s = backtest.realStrategies.find(s => s.name === val)
    const tf = s?.timeframe
    if (tf && tf !== cfg.value.timeframe) {
      cfg.value.timeframe = tf
    }
    // 同步到 store.strategies（后端需要数组）
    cfg.value.strategies = [val]
  } else {
    cfg.value.strategies = []
  }
}

// ---------- 数据源 ----------
const dataSourceOptions = [
  { label: 'SQLite（实盘库）', value: 'sqlite' },
  { label: 'kline（历史下载）', value: 'kline' },
]

/** kline 数据范围信息 */
const klineRange = ref<KlineRangeInfo | null>(null)
const klineRangeLoading = ref(false)

/** 需要查询的周期列表（主周期 + 可能的 H4/H1 MTF 依赖） */
const klineQueryTimeframes = computed(() => {
  const tf = cfg.value.timeframe
  const tfs = [tf]
  // 常见 MTF 依赖周期
  if (!tfs.includes('H4')) tfs.push('H4')
  if (!tfs.includes('H1')) tfs.push('H1')
  return tfs.join(',')
})

/** 数据源信息展示文本 */
const dataSourceInfo = computed(() => {
  if (cfg.value.data_source === 'sqlite') {
    return {
      symbol: 'XAUUSD',
      earliest: '—（SQLite 覆盖取决于实盘启动时间，通常较浅）',
      timeframe: cfg.value.timeframe,
    }
  }
  // kline
  if (!klineRange.value) return { symbol: 'XAUUSD', earliest: '加载中…', timeframe: cfg.value.timeframe }
  const common = klineRange.value.common_start_date
    ? `${klineRange.value.common_start_date} ~ ${klineRange.value.common_end_date}`
    : '无数据'
  return {
    symbol: klineRange.value.symbol || 'XAUUSD',
    earliest: common,
    timeframe: cfg.value.timeframe,
  }
})

/** 拉取 kline 范围 */
async function fetchKlineRange() {
  if (cfg.value.data_source !== 'kline') {
    klineRange.value = null
    return
  }
  klineRangeLoading.value = true
  try {
    klineRange.value = await getKlineRange(klineQueryTimeframes.value)
  } catch {
    klineRange.value = null
  } finally {
    klineRangeLoading.value = false
  }
}

// 数据源或周期变化时重新拉取
watch(() => cfg.value.data_source, fetchKlineRange)
watch(() => cfg.value.timeframe, fetchKlineRange)

/** 配置直接绑定 store.config */
const cfg = computed(() => backtest.config)

/** 单边成本合计 */
const costTotal = computed(() => (cfg.value.commission + cfg.value.slippage).toFixed(3))

// ---------- 组合指标 ----------
const logicOptions = [
  { label: t('backtest.logic_and'), value: 'AND' },
  { label: t('backtest.logic_or'), value: 'OR' },
  { label: t('backtest.logic_vote'), value: 'VOTE' },
]
const indicatorOptions = computed(() =>
  backtest.indicators.map(i => ({ label: i.label, value: i.key })))
const indicatorMenuOptions = computed(() =>
  backtest.indicators.map(i => ({ label: i.label, key: i.key })))

function paramDef(condIdx: number) {
  const c = backtest.combo.conditions[condIdx]
  if (!c) return []
  const def = backtest.indicators.find(i => i.key === c.indicator)
  return def?.params || []
}

const comboName = ref('')
const saving = ref(false)

async function saveComboAsStrategyFile() {
  const name = comboName.value.trim()
  if (!name) { message.warning(t('backtest.combo_name_required')); return }
  if (!backtest.combo.conditions.length) { message.warning(t('backtest.combo_empty')); return }
  saving.value = true
  try {
    const r = await backtest.saveCombo(name, cfg.value.timeframe)
    if (r.ok) {
      message.success(t('backtest.combo_saved', { file: r.file || name }), { duration: 6000 })
      await backtest.fetchStrategies()
      selectedStrategy.value = name
      cfg.value.strategies = [name]
      mode.value = 'live'
    } else {
      message.error(r.error || r.message || t('backtest.combo_save_failed'))
    }
  } catch (e: any) {
    message.error(e?.message || t('backtest.combo_save_failed'))
  }
  saving.value = false
}

// ---------- 公式策略 ----------
const formulaSaving = ref(false)

function saveFormulaAsFile() {
  const name = cfg.value.formulaName.trim()
  const formula = cfg.value.formula.trim()
  if (!name) { message.warning(t('backtest.combo_name_required')); return }
  if (!formula) { message.warning(t('backtest.formula_invalid', { msg: t('backtest.formula_empty') })); return }
  formulaSaving.value = true
  backtest.saveFormula(name, cfg.value.timeframe, formula).then(r => {
    if (r.ok) {
      message.success(t('backtest.formula_saved', { name: r.name || name }), { duration: 6000 })
      void backtest.fetchStrategies()
      selectedStrategy.value = name
      cfg.value.strategies = [name]
      mode.value = 'live'
    } else {
      message.error(t('backtest.formula_invalid', { msg: r.error || 'unknown' }))
    }
  }).catch((e: any) => {
    message.error(e?.message || t('backtest.combo_save_failed'))
  }).finally(() => { formulaSaving.value = false })
}

// ---------- 运行 ----------
const submitting = ref(false)
const fetching = ref(false)
let fetchPollTimer: ReturnType<typeof setInterval> | null = null

function canRun() {
  if (mode.value === 'combo') return backtest.combo.conditions.length > 0
  if (mode.value === 'formula') return cfg.value.formula.trim().length > 0
  return !!selectedStrategy.value
}

function gapText(gap: ExternalDataCoverage): string {
  const pct = Math.round((gap.coverage_ratio || 0) * 100)
  return `${gap.symbol} · ${gap.timeframe} · ${gap.start_date} ~ ${gap.end_date} — ${t('backtest.data_gap_detail', { bars: gap.sources?.backtest_sample?.bars_in_range ?? 0, expected: gap.expected_bars, pct })}`
}

function showDataGapDialog(gap: ExternalDataCoverage) {
  dialog.warning({
    title: t('backtest.data_gap_title'),
    content: () => h('div', { style: 'white-space: pre-line' },
      `${t('backtest.data_gap_body')}\n${gapText(gap)}`),
    positiveText: t('backtest.fetch_external_data'),
    negativeText: t('backtest.fill_data_continue'),
    onPositiveClick: () => { fetchExternal() },
    onNegativeClick: () => { run(true) },
  })
}

async function run(force = false) {
  if (!canRun()) {
    if (mode.value === 'combo') message.warning(t('backtest.combo_empty'))
    else if (mode.value === 'formula') message.warning(t('backtest.formula_empty'))
    else message.warning('请先选择一个策略')
    return
  }
  if (fetching.value) {
    message.warning(t('backtest.fetching_data'))
    return
  }
  submitting.value = true
  try {
    const payload: Record<string, any> = {
      strategies: mode.value === 'combo' ? ['combo'] : (mode.value === 'formula' ? ['formula'] : [selectedStrategy.value]),
      timeframe: cfg.value.timeframe,
      start_date: cfg.value.start_date,
      end_date: cfg.value.end_date,
      initial_cash: cfg.value.initial_cash,
      commission: cfg.value.commission,
      slippage: cfg.value.slippage,
      leverage: cfg.value.leverage,
      force,
      data_source: cfg.value.data_source || 'sqlite',
    }
    if (mode.value === 'combo') payload.combo = backtest.combo
    if (mode.value === 'formula') {
      payload.formula = cfg.value.formula
      payload.formula_name = cfg.value.formulaName || '公式策略'
    }
    const res = await backtest.submit(payload as any)
    if (res?.data_gap) {
      showDataGapDialog(res.data_gap)
    }
  } catch (e: any) {
    message.error(e?.message || t('backtest.submit_failed'))
  }
  submitting.value = false
}

function stop() {
  backtest.stop()
  message.info(t('backtest.stopped_hint'))
}

async function checkAndFetch() {
  if (fetching.value) { message.warning(t('backtest.fetching_data')); return }
  try {
    const cov = await getExternalDataCoverage({
      symbol: 'XAUUSD',
      timeframe: cfg.value.timeframe,
      start_date: cfg.value.start_date,
      end_date: cfg.value.end_date,
    })
    if (cov.sufficient) {
      message.success(t('externalData.coverage_ok', { pct: Math.round((cov.coverage_ratio || 0) * 100) }))
      return
    }
    showDataGapDialog(cov)
  } catch (e: any) {
    message.error(e?.message || t('backtest.fetch_failed'))
  }
}

async function fetchExternal() {
  fetching.value = true
  try {
    const res = await fetchExternalData({
      symbol: 'XAUUSD',
      timeframes: [cfg.value.timeframe],
      start_date: cfg.value.start_date,
      end_date: cfg.value.end_date,
    })
    if (res.error) {
      message.error(res.message || res.error, { duration: 8000 })
      fetching.value = false
      return
    }
    const jobId = res.job_id
    message.info(t('backtest.fetching_data'))
    if (fetchPollTimer) clearInterval(fetchPollTimer)
    fetchPollTimer = setInterval(async () => {
      try {
        const s = await getExternalDataStatus(jobId)
        if (s.status === 'completed') {
          clearInterval(fetchPollTimer!)
          fetchPollTimer = null
          fetching.value = false
          const tfRes = s.result?.[cfg.value.timeframe]
          if (tfRes?.status === 'ok') {
            message.success(t('backtest.data_ready', { bars: tfRes.fetched ?? 0 }), { duration: 5000 })
            run()
          } else {
            message.error(t('backtest.fetch_failed') + ': ' + (tfRes?.error || 'unknown'))
          }
        } else if (s.status === 'failed') {
          clearInterval(fetchPollTimer!)
          fetchPollTimer = null
          fetching.value = false
          message.error(t('backtest.fetch_failed') + ': ' + (s.error || ''))
        }
      } catch { /* 轮询失败忽略，下轮重试 */ }
    }, 2000)
  } catch (e: any) {
    fetching.value = false
    message.error(e?.message || t('backtest.fetch_failed'))
  }
}

onMounted(async () => {
  await Promise.all([backtest.fetchStrategies(), backtest.fetchIndicators()])
  // 恢复之前选中的策略
  if (cfg.value.strategies.length > 0) {
    selectedStrategy.value = cfg.value.strategies[0]
  }
  fetchKlineRange()
})

onUnmounted(() => {
  if (fetchPollTimer) { clearInterval(fetchPollTimer); fetchPollTimer = null; fetching.value = false }
})
</script>

<template>
  <n-card :title="$t('backtest.parameters')" size="small">
    <n-tabs v-model:value="mode" type="segment" size="small" animated>
      <!-- ========== A. 现有策略回测 ========== -->
      <n-tab-pane name="live" :tab="$t('backtest.mode_live')" />

      <!-- ========== B. 组合指标回测 ========== -->
      <n-tab-pane name="combo" :tab="$t('backtest.mode_combo')">
        <div style="margin-top: 12px;">
          <n-space align="center" :size="12" style="margin-bottom: 12px;">
            <span class="mini-label">{{ $t('backtest.combo_logic') }}</span>
            <n-select v-model:value="backtest.combo.logic" :options="logicOptions"
                      size="small" style="width: 150px;" />
            <template v-if="backtest.combo.logic === 'VOTE'">
              <span class="mini-label">{{ $t('backtest.min_votes') }}</span>
              <app-input-number v-model:value="backtest.combo.min_votes" :min="1" :max="10"
                                size="small" style="width: 110px;" />
            </template>
          </n-space>

          <div v-for="(c, idx) in backtest.combo.conditions" :key="idx" class="cond-row">
            <n-switch v-model:value="c.enabled" size="small" />
            <n-select :value="c.indicator" :options="indicatorOptions" size="small"
                      style="width: 190px;"
                      @update:value="(v: string) => backtest.setConditionIndicator(idx, v)" />
            <template v-for="p in paramDef(idx)" :key="p.key">
              <span class="mini-label">{{ p.label }}</span>
              <app-input-number
                v-model:value="c.params[p.key]"
                :min="p.min" :max="p.max" :step="p.step || 1"
                size="small" style="width: 96px;" />
            </template>
            <n-button size="tiny" quaternary type="error" @click="backtest.removeComboCondition(idx)">
              {{ $t('common.delete') }}
            </n-button>
          </div>

          <n-empty v-if="!backtest.combo.conditions.length"
                   :description="$t('backtest.combo_empty')" style="padding: 18px 0;" />

          <n-space :size="10" style="margin-top: 12px;">
            <n-dropdown trigger="click" :options="indicatorMenuOptions"
                        @select="(k: string) => backtest.addComboCondition(k)">
              <n-button size="small" type="primary" ghost>
                + {{ $t('backtest.combo_add') }}
              </n-button>
            </n-dropdown>
            <n-input v-model:value="comboName" size="small" :placeholder="$t('backtest.combo_name_ph')"
                     style="width: 220px;" />
            <n-button size="small" :loading="saving" :disabled="!backtest.combo.conditions.length"
                      @click="saveComboAsStrategyFile">
              {{ $t('backtest.combo_save') }}
            </n-button>
          </n-space>
        </div>
      </n-tab-pane>

      <!-- ========== C. 公式策略回测 ========== -->
      <n-tab-pane name="formula" :tab="$t('backtest.mode_formula')">
        <div style="margin-top: 12px;">
          <n-form label-placement="top" size="small">
            <n-form-item :label="$t('backtest.formula_label')" :feedback="$t('backtest.formula_hint')">
              <n-input
                v-model:value="cfg.formula"
                type="textarea"
                :placeholder="$t('backtest.formula_placeholder')"
                :autosize="{ minRows: 2, maxRows: 4 }"
                style="font-family: var(--font-mono);"
              />
            </n-form-item>
            <n-form-item :label="$t('backtest.combo_name_ph')">
              <n-input v-model:value="cfg.formulaName" size="small"
                       :placeholder="$t('backtest.formula_name_ph')" style="width: 280px;" />
            </n-form-item>
          </n-form>
          <n-space :size="10">
            <n-button size="small" type="primary" ghost :loading="formulaSaving"
                      @click="saveFormulaAsFile">
              {{ $t('backtest.formula_save') }}
            </n-button>
          </n-space>
        </div>
      </n-tab-pane>
    </n-tabs>

    <!-- 公共参数 -->
    <n-form label-placement="left" label-width="96" size="small" style="margin-top: 14px;">
      <!-- 三选 + 日期 + 四配置项：网格布局，保证列对齐 -->
      <div class="layout-grid">
        <!-- Row 1: 策略 | 数据源 | 周期 -->
        <div class="select-item">
          <label class="config-label">策略</label>
          <n-select
            :value="selectedStrategy"
            filterable clearable size="small"
            :options="strategySelectOptions"
            placeholder="选择策略"
            @update:value="onStrategySelect"
          />
        </div>
        <div class="select-item">
          <label class="config-label">数据源</label>
          <n-select v-model:value="cfg.data_source" :options="dataSourceOptions" size="small" />
        </div>
        <div class="select-item">
          <label class="config-label">周期</label>
          <n-select
            :value="cfg.timeframe"
            :options="timeframeOptions"
            size="small"
            :disabled="timeframeLocked"
          />
        </div>

        <!-- Row 2: 开始日期(col1) | 四配置项+总成本(span col2-3, 与数据源同列) -->
        <div class="select-item">
          <label class="config-label">{{ $t('backtest.start_date') }}</label>
          <n-date-picker v-model:formatted-value="cfg.start_date" type="date" value-format="yyyy-MM-dd" size="small" style="width: 100%;" />
        </div>
        <div class="config-group">
          <div class="config-item">
            <label class="config-label">{{ $t('backtest.initial_cash') }}</label>
            <app-input-number v-model:value="cfg.initial_cash" :min="100" :step="1000" size="tiny" class="config-spinner config-spinner-wide" />
          </div>
          <div class="config-item">
            <label class="config-label">{{ $t('backtest.commission') }}%</label>
            <app-input-number v-model:value="cfg.commission" :min="0" :step="0.01" :precision="3" size="tiny" class="config-spinner" />
          </div>
          <div class="config-item">
            <label class="config-label">{{ $t('backtest.slippage') }}%</label>
            <app-input-number v-model:value="cfg.slippage" :min="0" :step="0.01" :precision="3" size="tiny" class="config-spinner" />
          </div>
          <div class="config-item">
            <label class="config-label">{{ $t('backtest.leverage') }}</label>
            <app-input-number v-model:value="cfg.leverage" :min="1" :max="30" :step="1" size="tiny" class="config-spinner" />
          </div>
          <div class="config-item">
            <label class="config-label">{{ $t('backtest.cost_total') }}</label>
            <n-tag size="small" type="warning" :bordered="false" class="cost-tag">{{ costTotal }}%</n-tag>
          </div>
        </div>

        <!-- Row 3: 结束日期(col1) -->
        <div class="select-item">
          <label class="config-label">{{ $t('backtest.end_date') }}</label>
          <n-date-picker v-model:formatted-value="cfg.end_date" type="date" value-format="yyyy-MM-dd" size="small" style="width: 100%;" />
        </div>
      </div>

      <!-- 数据源信息展示 -->
      <div class="ds-info">
        <span class="ds-tag">品种: {{ dataSourceInfo.symbol }}</span>
        <span class="ds-tag">可用范围: <template v-if="cfg.data_source === 'kline' && klineRangeLoading">加载中…</template><template v-else>{{ dataSourceInfo.earliest }}</template></span>
      </div>

      <!-- 运行按钮 -->
      <n-grid :cols="4" :x-gap="12" style="margin-top: 10px;">
        <n-gi :span="backtest.loading ? 2 : 3">
          <n-button type="primary" :loading="submitting || backtest.loading"
                    @click="run(false)" :disabled="backtest.loading || fetching" block>
            {{ backtest.loading ? backtest.progress || $t('backtest.running') : $t('backtest.run_backtest') }}
          </n-button>
        </n-gi>
        <n-gi v-if="backtest.loading" :span="1">
          <n-button type="warning" @click="stop" block>
            {{ $t('backtest.stop') }}
          </n-button>
        </n-gi>
        <n-gi :span="1">
          <n-button :loading="fetching" :disabled="backtest.loading || submitting"
                    @click="checkAndFetch" block>
            {{ $t('backtest.fetch_external_data') }}
          </n-button>
        </n-gi>
      </n-grid>
    </n-form>

    <!-- 错误 -->
    <n-alert v-if="backtest.error" type="error" :title="backtest.error" closable
             style="margin-top: 12px;" @close="backtest.reset()" />
  </n-card>
</template>

<style scoped>
.cost-tag {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}
.mini-label {
  font-size: 12px;
  opacity: 0.65;
  white-space: nowrap;
}
.cond-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 8px 10px;
  margin-bottom: 8px;
  border: 1px solid var(--n-border-color, rgba(128, 128, 128, 0.22));
  border-radius: 8px;
}
.ds-info {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: center;
  margin: 8px 0;
}
.ds-tag {
  font-size: 12px;
  opacity: 0.75;
  white-space: nowrap;
}

/* 三选 + 日期 + 四配置项：3 列网格，保证垂直对齐 */
.layout-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  column-gap: 14px;
  row-gap: 8px;
  margin-bottom: 8px;
}
.select-item {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* Row 2: 四配置项+总成本横排在 col 2-3，与数据源同列起始 */
.config-group {
  grid-column: 2 / 4;
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.config-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}
.config-label {
  font-size: 14px;
  opacity: 1;
  white-space: nowrap;
  margin-bottom: 2px;
}
/* 初始资金宽度略宽，其余三个更窄 */
.config-spinner {
  width: 42px;
}
.config-spinner-wide {
  width: 52px;
}
</style>
