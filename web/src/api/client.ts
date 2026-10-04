// REST API 客户端
import axios from 'axios'
import type { AccountInfo, Position, Candle, TickPrice, LogEntry, EngineStatus, BacktestRequest, BacktestJob, BacktestResult, BacktestHistoryItem, ClosedTrade, TradeStats, TradeAnalysis, LlmStatus, ExternalDataCoverage } from '@/types'

const http = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: { 'X-AlgoForge-Local': '1' },
})

// 原生 fetch 统一封装（审计 M-8 第一步）：
// - 10s 超时（fetch 默认永不超时 → 后端挂起时无限 pending）
// - AbortController 可控取消
// - 自动带 X-AlgoForge-Local 头（危险写接口的 403 闸门），避免各调用点漏加
// 后续批次把其余原生 fetch 调用点逐步迁到这里。
export async function apiFetch(path: string, init: RequestInit = {}, timeoutMs = 10000): Promise<Response> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const headers = new Headers(init.headers || {})
    if (!headers.has('X-AlgoForge-Local')) headers.set('X-AlgoForge-Local', '1')
    return await fetch(path, { ...init, headers, signal: ctrl.signal })
  } finally {
    clearTimeout(timer)
  }
}

// === 引擎 ===
export async function getEngineStatus(): Promise<EngineStatus> {
  const { data } = await http.get('/engine/status')
  return data
}

export async function startEngine(): Promise<void> {
  await http.post('/engine/start')
}

export async function stopEngine(): Promise<void> {
  await http.post('/engine/stop')
}

export async function restartEngine(): Promise<{ status: string }> {
  // stop() 内部 join 最长 ~16s，单独放宽超时避免全局 10s 造成虚假失败提示
  const { data } = await http.post('/engine/restart', null, { timeout: 30000 })
  return data
}

// === 账户 ===
export async function getAccount(): Promise<AccountInfo> {
  const { data } = await http.get('/account')
  return data
}

// === 持仓 ===
export async function getPositions(timeoutMs = 10000): Promise<Position[]> {
  const { data } = await http.get('/positions', { timeout: timeoutMs })
  return data
}

export async function closePosition(ticket: number, volume?: number): Promise<void> {
  // 平仓走 MT4 桥接命令（可能触发 10s 超时 + 2 次重试 ~20s），单独放宽 timeout
  await http.post(`/positions/${ticket}/close`, { volume }, { timeout: 30000 })
}

export async function modifyPosition(ticket: number, sl?: number, tp?: number): Promise<void> {
  await http.post(`/positions/${ticket}/modify`, { sl, tp })
}

// === 配置 ===
export async function getConfig(): Promise<Record<string, any>> {
  const { data } = await http.get('/config')
  return data
}

export async function updateConfig(updates: Record<string, any>): Promise<void> {
  await http.post('/config', { updates })
}

export async function resetConfig(key?: string): Promise<void> {
  await http.post('/config/reset', { key })
}

// === 策略池 ===
export async function getStrategyPool(): Promise<Record<string, any>> {
  const { data } = await http.get('/config/strategy-pool')
  return data
}

export async function updateStrategyPool(pool: Record<string, any>): Promise<void> {
  await http.post('/config/strategy-pool', { pool })
}

// === 协调器 ===
export async function getCoordinator(): Promise<Record<string, any>> {
  const { data } = await http.get('/config/coordinator')
  return data
}

export async function updateCoordinator(cfg: Record<string, any>): Promise<void> {
  await http.post('/config/coordinator', { config: cfg })
}

// === 纸面交易配置 ===
export async function getPaperConfig(): Promise<any> {
  const { data } = await http.get('/config/paper')
  return data
}

export async function updatePaperConfig(cfg: Record<string, any>): Promise<Record<string, any>> {
  const { data } = await http.post('/config/paper', { config: cfg })
  return data
}

export async function resetPaperData(): Promise<void> {
  await http.post('/paper-trading/reset')
}

// === 行情 ===
export async function getPrice(): Promise<TickPrice> {
  const { data } = await http.get('/market/price')
  return data
}

export async function getCandles(timeframe = 'H1', count = 100): Promise<Candle[]> {
  const { data } = await http.get('/market/candles', { params: { timeframe, count } })
  return data
}

// === 新闻过滤 ===
export async function getNewsCalendar(): Promise<{
  is_blackout: boolean
  blackout_reason: string
  upcoming_events: Array<{
    title: string
    country: string
    impact: string
    datetime: string
    forecast: string
    previous: string
  }>
  blackout_windows: Array<{ start: string; end: string; title: string }>
}> {
  const { data } = await http.get('/news/calendar')
  return data
}

// === 日志 ===
export async function getLogs(level?: string, limit = 100, since?: string): Promise<LogEntry[]> {
  const { data } = await http.get('/logs', { params: { level, limit, since } })
  return data.logs
}

// === 历史成交 ===
export async function getTradeHistory(limit = 100, offset = 0, mode?: string): Promise<{ trades: ClosedTrade[]; total: number }> {
  const params: any = { limit, offset }
  if (mode) params.mode = mode
  const { data } = await http.get('/trades/history', { params })
  return data
}

// === 策略收益统计 ===
export async function getTradeStats(params?: {
  strategies?: string
  from_date?: string
  to_date?: string
}): Promise<TradeStats> {
  const { data } = await http.get('/trades/stats', { params })
  return data
}

export async function getLlmStatus(): Promise<LlmStatus> {
  const { data } = await http.get('/llm/status')
  return data
}

export async function getTradeAnalysis(ticket: number, ai: boolean = false): Promise<TradeAnalysis> {
  // ai=true 时 LLM 分析生成可能耗时 ~40s，放宽单次请求超时
  const { data } = await http.get(`/trades/analysis/${ticket}`, {
    params: { ai },
    timeout: ai ? 60000 : 10000,
  })
  return data
}

export async function getTradeReport(): Promise<any> {
  const { data } = await http.get('/trades/report')
  return data
}

export async function getSignals(params?: { strategy?: string; status?: string; limit?: number }): Promise<any[]> {
  const { data } = await http.get('/signals', { params })
  return data
}

// === 报告 ===
export async function getReports(params?: {
  type?: string
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}): Promise<any> {
  const { data } = await http.get('/reports', { params })
  return data
}

export async function getReportById(id: number): Promise<any> {
  const { data } = await http.get(`/reports/${id}`)
  return data
}

export async function getReportTimeline(date: string, type = 'daily'): Promise<any> {
  const { data } = await http.get(`/reports/timeline/${date}`, { params: { type } })
  return data
}

export async function generateReport(type = 'daily', date?: string): Promise<any> {
  const { data } = await http.post('/reports/generate', null, { params: { type, date } })
  return data
}

// === 新闻预判报告（已迁移至 gold_news 系统） ===

// === 回测 ===
export async function runBacktest(params: BacktestRequest): Promise<{ job_id: string; status: string; data_gap?: ExternalDataCoverage }> {
  const { data } = await http.post('/backtest/run', params)
  return data
}

// === 外部数据补充渠道（Twelve Data） ===
export async function fetchExternalData(params: {
  symbol?: string
  timeframes: string[]
  start_date: string
  end_date?: string
}): Promise<{ job_id: string; status: string; error?: string; message?: string }> {
  const { data } = await http.post('/external_data/fetch', params)
  return data
}

export async function getExternalDataStatus(jobId: string): Promise<{
  job_id: string
  status: string
  progress?: string
  error?: string
  result?: Record<string, { status: string; fetched?: number; total?: number; sample_exported?: string | null; error?: string }>
}> {
  const { data } = await http.get(`/external_data/status/${jobId}`)
  return data
}

export async function getExternalDataCoverage(params: {
  symbol?: string
  timeframe: string
  start_date: string
  end_date?: string
}): Promise<ExternalDataCoverage> {
  const { data } = await http.get('/external_data/coverage', { params })
  return data
}

export async function getExternalApiKeyStatus(): Promise<{ configured: boolean; source: string | null; key_file: string }> {
  const { data } = await http.get('/external_data/api_key_status')
  return data
}

export async function getBacktestStatus(jobId: string): Promise<BacktestJob> {
  const { data } = await http.get(`/backtest/status/${jobId}`)
  return data
}

export async function getBacktestResults(jobId: string): Promise<BacktestJob & { result?: BacktestResult }> {
  const { data } = await http.get(`/backtest/results/${jobId}`)
  return data
}

export async function getBacktestHistory(limit = 20): Promise<BacktestHistoryItem[]> {
  const { data } = await http.get('/backtest/history', { params: { limit } })
  return data
}

// === v6：策略清单 / 指标清单 / 组合保存 / AI 解读 ===

export interface BacktestStrategyItem {
  name: string
  timeframe: string
  magic: number
}

export async function getBacktestStrategies(): Promise<{
  builtin: BacktestStrategyItem[]
  real: BacktestStrategyItem[]
  error?: string | null
}> {
  const { data } = await http.get('/backtest/strategies')
  return data
}

/** v12：查询 kline parquet 可用时间范围 */
export interface KlineRangeInfo {
  symbol: string
  per_timeframe: Record<string, {
    available: boolean
    start_date: string | null
    end_date: string | null
  }>
  common_start_date?: string
  common_end_date?: string
}

export async function getKlineRange(timeframes: string): Promise<KlineRangeInfo> {
  const { data } = await http.get('/backtest/kline-range', { params: { timeframes } })
  return data
}

export interface IndicatorParam {
  key: string
  label: string
  default: number
  min?: number
  max?: number
  step?: number
}

export interface IndicatorDef {
  key: string
  label: string
  desc?: string
  params: IndicatorParam[]
}

export async function getBacktestIndicators(): Promise<{ indicators: IndicatorDef[] }> {
  const { data } = await http.get('/backtest/indicators')
  return data
}

export interface ComboCondition {
  indicator: string
  params: Record<string, number>
  enabled?: boolean
}

export interface ComboConfig {
  logic: 'AND' | 'OR' | 'VOTE'
  min_votes?: number
  conditions: ComboCondition[]
}

export async function saveComboAsStrategy(payload: {
  name: string
  timeframe: string
  combo: ComboConfig
}): Promise<{ ok: boolean; file?: string; path?: string; error?: string; message?: string }> {
  const { data } = await http.post('/backtest/combo/save', payload)
  return data
}

export async function interpretBacktest(jobId: string): Promise<{
  ok: boolean
  text?: string
  provider?: string
  model?: string
  error?: string
  bullets?: string[]
}> {
  const { data } = await http.post(`/backtest/interpret/${jobId}`)
  return data
}

// === v7：公式策略保存为策略文件 ===
export interface SaveFormulaPayload {
  name: string
  timeframe: string
  formula: string
}

export async function saveFormulaAsStrategy(payload: SaveFormulaPayload): Promise<{
  ok: boolean
  path?: string
  name?: string
  hint?: string
  error?: string
}> {
  const { data } = await http.post('/backtest/formula/save', payload)
  return data
}

export interface VersionInfo {
  version: string
  commit: string
  branch: string
  dirty: boolean
  display: string
  has_update: boolean
  behind_count: number
}

export async function getVersionInfo(): Promise<VersionInfo> {
  const { data } = await http.get('/version')
  return data
}

export interface ChangelogCommit {
  hash: string
  date: string
  subject: string
}

export async function getChangelog(limit = 20): Promise<{ commits: ChangelogCommit[]; error?: string }> {
  const { data } = await http.get('/version/changelog', { params: { limit } })
  return data
}

export async function getRemoteChangelog(limit = 20): Promise<{ commits: ChangelogCommit[] }> {
  const { data } = await http.get('/version/remote-changelog', { params: { limit } })
  return data
}

export async function updateVersion(): Promise<{ success: boolean; message: string; version?: VersionInfo }> {
  const { data } = await http.post('/version/update')
  return data
}

export async function rollbackVersion(): Promise<{ success: boolean; message: string }> {
  const { data } = await http.post('/version/rollback')
  return data
}

export interface UpdateConfig {
  auto_update_enabled: boolean
  update_interval_hours: number
}

export async function getUpdateConfig(): Promise<UpdateConfig> {
  const { data } = await http.get('/version/update-config')
  return data
}

export async function setUpdateConfig(config: { auto_update_enabled?: boolean; update_interval_hours?: number }): Promise<UpdateConfig> {
  const { data } = await http.post('/version/update-config', config)
  return data
}

export interface UpdateState {
  state: 'idle' | 'fetching' | 'pending' | 'applying' | 'restarting' | 'healthy' | 'rolling_back'
  current_version: string
  remote_version: string | null
  remote_commit: string | null
  remote_ahead: number
  message: string | null
  error: string | null
}

export async function getUpdateState(): Promise<UpdateState> {
  const { data } = await http.get('/version/update-state')
  return data
}

export interface BiasState {
  direction: 'bullish' | 'bearish' | 'neutral' | null
  score: number
  updated_at: number
  source: string
  age_seconds: number | null
}

export async function getBiasState(): Promise<BiasState> {
  const { data } = await http.get('/version/bias-state')
  return data
}

export async function forceRefreshBias(): Promise<{ direction: string | null; full: BiasState }> {
  const { data } = await http.post('/version/bias-state/refresh')
  return data
}
