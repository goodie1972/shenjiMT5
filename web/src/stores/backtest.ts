import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import {
  runBacktest, getBacktestStatus, getBacktestResults, getBacktestHistory,
  getBacktestStrategies, getBacktestIndicators, saveComboAsStrategy, interpretBacktest,
  saveFormulaAsStrategy,
} from '@/api/client'
import type {
  BacktestStrategyItem, IndicatorDef, ComboConfig,
} from '@/api/client'
import type { ExternalDataCoverage } from '@/types'
import type { BacktestRequest, BacktestResult, BacktestHistoryItem } from '@/types'

export const useBacktestStore = defineStore('backtest', () => {
  const jobId = ref<string | null>(null)
  const status = ref<'idle' | 'queued' | 'running' | 'completed' | 'failed'>('idle')
  const phase = ref('')                 // v3：queued/data/compute/stats/done/failed
  const logTail = ref<string[]>([])     // v3：日志尾随
  const progress = ref('')
  const error = ref<string | null>(null)
  const result = ref<BacktestResult | null>(null)
  const history = ref<BacktestHistoryItem[]>([])
  const stopped = ref(false)            // 软停止标记：停止后忽略后续结果

  // v6：策略清单 / 指标清单 / 组合配置 / AI 解读
  const builtinStrategies = ref<BacktestStrategyItem[]>([])
  const realStrategies = ref<BacktestStrategyItem[]>([])
  const indicators = ref<IndicatorDef[]>([])
  const combo = ref<ComboConfig>({ logic: 'VOTE', min_votes: 1, conditions: [] })
  const aiText = ref<string | null>(null)
  const aiLoading = ref(false)
  const aiMeta = ref<{ provider?: string; model?: string } | null>(null)
  const aiError = ref<string | null>(null)

  // v7：面板配置持久化（localStorage）——含杠杆、公式等，刷新后保留上次设置
  const STORAGE_KEY = 'algoforge.backtest.config.v7'
  const defaultConfig = {
    timeframe: 'M30',
    start_date: '2026-03-23',
    end_date: '2026-09-07',
    initial_cash: 10000,
    commission: 0.02,
    slippage: 0.01,
    leverage: 3,
    formula: '',
    formulaName: '',
    strategies: [] as string[],
    data_source: 'sqlite' as 'sqlite' | 'kline',  // v11
  }
  const config = ref<typeof defaultConfig>({ ...defaultConfig })

  function loadConfig() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw)
        config.value = { ...defaultConfig, ...parsed }
      }
    } catch { /* ignore corrupt storage */ }
  }
  function saveConfig() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(config.value))
    } catch { /* ignore quota / private mode */ }
  }
  loadConfig()
  watch(config, saveConfig, { deep: true })

  const loading = computed(() => status.value === 'queued' || status.value === 'running')

  let pollTimer: ReturnType<typeof setInterval> | null = null

  async function submit(params: BacktestRequest): Promise<{ data_gap?: ExternalDataCoverage } | undefined> {
    status.value = 'queued'
    phase.value = 'queued'
    logTail.value = []
    progress.value = '提交中...'
    error.value = null
    result.value = null
    stopped.value = false

    try {
      const res = await runBacktest(params)
      if (res.data_gap) {
        // 数据缺失/不完整：不启动回测，交由面板弹窗引导补全
        status.value = 'idle'
        phase.value = ''
        progress.value = ''
        return { data_gap: res.data_gap }
      }
      jobId.value = res.job_id
      status.value = 'queued'
      phase.value = 'queued'
      progress.value = '排队中...'
      startPolling()
    } catch (e: any) {
      status.value = 'failed'
      error.value = e?.response?.data?.detail || e?.message || '提交回测失败'
    }
  }

  function startPolling() {
    stopPolling()
    pollTimer = setInterval(async () => {
      if (!jobId.value) return
      try {
        const s = await getBacktestStatus(jobId.value)
        if (stopped.value) return   // 软停止后忽略
        status.value = s.status as any
        phase.value = s.phase || ''
        logTail.value = s.log_tail || []
        progress.value = s.progress || ''
        if (s.error) error.value = s.error
        if (s.status === 'completed') {
          stopPolling()
          await loadResults()
        } else if (s.status === 'failed') {
          stopPolling()
          error.value = s.error || '回测失败'
        }
      } catch {
        // ignore polling errors
      }
    }, 1000)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  /** 软停止：停止轮询并忽略后续结果（后端线程无法强杀，仅前端放弃等待） */
  function stop() {
    stopped.value = true
    stopPolling()
    status.value = 'idle'
    phase.value = ''
    progress.value = ''
    logTail.value = [...logTail.value, '-- 已手动停止等待（后台任务将在完成后自行结束） --']
  }

  async function loadResults() {
    if (!jobId.value) return
    try {
      const res = await getBacktestResults(jobId.value)
      if (res.result) result.value = res.result
    } catch { /* ignore */ }
  }

  async function fetchHistory() {
    try {
      history.value = await getBacktestHistory()
    } catch { /* ignore */ }
  }

  // === v6 新增 ===

  async function fetchStrategies() {
    try {
      const d = await getBacktestStrategies()
      builtinStrategies.value = d.builtin || []
      realStrategies.value = d.real || []
    } catch { /* ignore */ }
  }

  async function fetchIndicators() {
    try {
      const d = await getBacktestIndicators()
      indicators.value = d.indicators || []
      // 首次加载给一个默认条件，避免面板空白
      if (!combo.value.conditions.length && d.indicators?.length) {
        const def = d.indicators[0]
        combo.value.conditions.push({
          indicator: def.key,
          enabled: true,
          params: Object.fromEntries((def.params || []).map(p => [p.key, p.default])),
        })
      }
    } catch { /* ignore */ }
  }

  /** 组合指标：动态添加条件 */
  function addComboCondition(indicatorKey?: string) {
    const def = indicators.value.find(i => i.key === indicatorKey) || indicators.value[0]
    if (!def) return
    combo.value.conditions.push({
      indicator: def.key,
      enabled: true,
      params: Object.fromEntries((def.params || []).map(p => [p.key, p.default])),
    })
  }

  /** 组合指标：切换条件所用指标时重置参数 */
  function setConditionIndicator(idx: number, indicatorKey: string) {
    const def = indicators.value.find(i => i.key === indicatorKey)
    if (!def) return
    combo.value.conditions[idx] = {
      indicator: def.key,
      enabled: combo.value.conditions[idx]?.enabled ?? true,
      params: Object.fromEntries((def.params || []).map(p => [p.key, p.default])),
    }
  }

  function removeComboCondition(idx: number) {
    combo.value.conditions.splice(idx, 1)
  }

  /** 一键把当前组合保存为策略文件 */
  async function saveCombo(name: string, timeframe: string) {
    return await saveComboAsStrategy({ name, timeframe, combo: combo.value })
  }

  /** v7：把公式策略落成一个策略文件（后端 /backtest/formula/save） */
  async function saveFormula(name: string, timeframe: string, formula: string) {
    return await saveFormulaAsStrategy({ name, timeframe, formula })
  }

  /** AI 解读（LLM；失败时前端保留规则模板） */
  async function requestAiInterpret() {
    if (!jobId.value) return
    aiLoading.value = true
    aiError.value = null
    try {
      const d = await interpretBacktest(jobId.value)
      if (d.ok && d.text) {
        aiText.value = d.text
        aiMeta.value = { provider: d.provider, model: d.model }
      } else {
        aiError.value = d.error || 'AI 解读失败'
      }
    } catch (e: any) {
      aiError.value = e?.response?.data?.detail || e?.message || 'AI 解读失败'
    } finally {
      aiLoading.value = false
    }
  }

  function reset() {
    stopPolling()
    jobId.value = null
    status.value = 'idle'
    phase.value = ''
    progress.value = ''
    error.value = null
    result.value = null
    logTail.value = []
    aiText.value = null
    aiError.value = null
    aiMeta.value = null
  }

  return {
    jobId, status, phase, logTail, progress, error, result, history,
    loading,
    builtinStrategies, realStrategies, indicators, combo,
    aiText, aiLoading, aiMeta, aiError,
    config, loadConfig, saveConfig,
    submit, fetchHistory, loadResults, stop, reset,
    fetchStrategies, fetchIndicators, addComboCondition, removeComboCondition,
    setConditionIndicator, saveCombo, saveFormula, requestAiInterpret,
  }
})
