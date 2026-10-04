<script setup lang="ts">
/**
 * BacktestEquityChart.vue — AM 风格资金曲线区
 * 头部小指标行 + 累计收益主图（面积） + 滚动夏普金色副图（时间轴双向同步）。
 * 数据来自后端 v3 series（均匀降采样含首尾）。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { createChart, ColorType, LineStyle, type UTCTimestamp, type IChartApi } from 'lightweight-charts'
import { useAppStore } from '@/stores/app'
import type { BacktestResult, BacktestSeries } from '@/types'

const props = defineProps<{ result: BacktestResult }>()
const { t } = useI18n()
const app = useAppStore()

const GOLD = '#f0b90b'
const PROFIT = '#0ecb81'
const LOSS = '#f6465d'

const mainContainer = ref<HTMLDivElement | null>(null)
const subContainer = ref<HTMLDivElement | null>(null)

const series = computed<BacktestSeries | null>(() => {
  const by = props.result.by_strategy || {}
  const name = Object.keys(by)[0]
  return name ? by[name]?.series ?? null : null
})
const first = computed(() => {
  const by = props.result.by_strategy || {}
  const name = Object.keys(by)[0]
  return name ? by[name] : null
})

const initialCash = computed(() => {
  // 由首点 equity + 首点收益率反推不可靠；直接用 total_return 与 equity 终值比例即可。
  // 此处用固定 10000 或后端 cost 无关——收益率 = (equity/e0 - 1)，e0 取 equity[0] - bar_pnl[0] 近似。
  // 简化：后端 equity 首点即 initial_cash + bar_pnl[0]，用 (equity[0] - bar_pnl[0]) 还原本金。
  const s = series.value
  if (!s || !s.equity.length) return 10000
  const e0 = s.equity[0] - (s.bar_pnl?.[0] ?? 0)
  return e0 > 0 ? e0 : 10000
})

const returnPct = computed(() => props.result.total_return_pct ?? 0)
const cumColor = computed(() => returnPct.value >= 0 ? PROFIT : LOSS)

function toTs(label: string): UTCTimestamp {
  return Math.floor(new Date(label.replace(' ', 'T')).getTime() / 1000) as UTCTimestamp
}

// ── 头部小指标 ──
const headStats = computed(() => [
  { label: t('backtest.equity_cum_return'), value: `${returnPct.value >= 0 ? '+' : ''}${returnPct.value.toFixed(2)}%`, color: cumColor.value },
  { label: t('backtest.max_drawdown'), value: `-${(first.value?.max_drawdown ?? 0).toFixed(2)}%`, color: LOSS },
  { label: t('backtest.stat_sharpe'), value: (first.value?.sharpe ?? props.result.sharpe_ratio ?? 0).toFixed(2) },
  { label: t('backtest.stat_sortino'), value: first.value?.sortino != null ? first.value.sortino.toFixed(2) : '—' },
  { label: t('backtest.equity_calmar'), value: first.value?.calmar != null ? first.value.calmar.toFixed(2) : '—' },
  { label: t('backtest.avg_hold'), value: first.value?.avg_hold_bars != null ? `${first.value.avg_hold_bars} bar` : '—' },
])

// ── 图表实例 ──
let mainChart: IChartApi | null = null
let subChart: IChartApi | null = null
let mainArea: any = null
let subLine: any = null
let resizeObs: ResizeObserver | null = null
const syncLock = { value: false }

function chartOptions(width: number, height: number, showScale: boolean) {
  const isDark = app.isDark
  return {
    layout: {
      background: { type: ColorType.Solid, color: isDark ? '#1a1d23' : '#ffffff' },
      textColor: isDark ? '#8b8f97' : '#555555',
    },
    grid: {
      vertLines: { color: isDark ? '#2d3139' : '#e8e8e8' },
      horzLines: { color: isDark ? '#2d3139' : '#e8e8e8' },
    },
    width, height,
    timeScale: {
      timeVisible: true,
      borderColor: isDark ? '#2d3139' : '#d0d0d0',
      visible: showScale,
    },
    rightPriceScale: { borderColor: isDark ? '#2d3139' : '#d0d0d0' },
    crosshair: { mode: 0 },
  }
}

function render() {
  const s = series.value
  if (!s || !mainContainer.value || !subContainer.value) return

  // 清理旧实例
  destroyCharts()

  const w = mainContainer.value.clientWidth
  mainChart = createChart(mainContainer.value, chartOptions(w, 300, false))
  mainArea = mainChart.addAreaSeries({
    lineColor: cumColor.value,
    topColor: cumColor.value + '44',
    bottomColor: cumColor.value + '05',
    lineWidth: 2,
    priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
  })
  mainArea.setData(
    s.labels.map((lb, i) => ({ time: toTs(lb), value: +(((s.equity[i] / initialCash.value) - 1) * 100).toFixed(3) }))
  )
  mainArea.createPriceLine({
    price: 0, color: 'rgba(128,128,128,0.4)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false,
  })

  const w2 = subContainer.value.clientWidth
  subChart = createChart(subContainer.value, chartOptions(w2, 120, true))
  subLine = subChart.addLineSeries({ color: GOLD, lineWidth: 2, priceFormat: { type: 'price', precision: 2, minMove: 0.01 } })
  subLine.setData(
    s.labels
      .map((lb, i) => ({ time: toTs(lb), value: s.rolling_sharpe[i] }))
      .filter((p): p is { time: UTCTimestamp; value: number } => p.value != null && isFinite(p.value))
  )
  subLine.createPriceLine({
    price: 0, color: 'rgba(128,128,128,0.4)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true,
  })

  // 时间轴双向同步（带锁防重入）
  mainChart.timeScale().subscribeVisibleLogicalRangeChange(r => {
    if (syncLock.value || !r || !subChart) return
    syncLock.value = true
    try { subChart.timeScale().setVisibleLogicalRange(r) } finally { syncLock.value = false }
  })
  subChart.timeScale().subscribeVisibleLogicalRangeChange(r => {
    if (syncLock.value || !r || !mainChart) return
    syncLock.value = true
    try { mainChart.timeScale().setVisibleLogicalRange(r) } finally { syncLock.value = false }
  })
}

function destroyCharts() {
  mainChart?.remove(); mainChart = null
  subChart?.remove(); subChart = null
}

function onResize() {
  if (mainChart && mainContainer.value) mainChart.applyOptions({ width: mainContainer.value.clientWidth })
  if (subChart && subContainer.value) subChart.applyOptions({ width: subContainer.value.clientWidth })
}

onMounted(() => {
  resizeObs = new ResizeObserver(onResize)
  if (mainContainer.value) resizeObs.observe(mainContainer.value)
})
onBeforeUnmount(() => {
  resizeObs?.disconnect()
  destroyCharts()
})

// immediate: true —— 父组件以 v-if="result" 挂载本组件，result 在挂载时已有值，
// 非 immediate 的 watch 永不触发（首测资金曲线空白的根因）
watch(() => props.result, () => nextTick(render), { deep: false, immediate: true })
watch(() => app.isDark, () => nextTick(render))
</script>

<template>
  <n-card :title="t('backtest.equity_title')" size="small">
    <template #header-extra>
      <n-space :size="8" align="center">
        <n-tag v-if="series?.sampled" size="small" type="default">
          {{ t('backtest.sampled_hint', { points: series.labels.length, total: series.n_bars }) }}
        </n-tag>
        <n-tag v-if="result.rolling_window" size="small" type="warning" :bordered="false">
          {{ t('backtest.equity_window', { n: result.rolling_window }) }}
        </n-tag>
      </n-space>
    </template>

    <!-- 头部小指标行 -->
    <div class="head-stats">
      <div v-for="st in headStats" :key="st.label" class="head-stat">
        <div class="hs-label">{{ st.label }}</div>
        <div class="hs-value" :style="st.color ? { color: st.color } : {}">{{ st.value }}</div>
      </div>
    </div>

    <!-- 主图：累计收益 -->
    <div ref="mainContainer" class="chart-main" />
    <!-- 副图：滚动夏普 -->
    <div class="sub-title">{{ t('backtest.equity_rolling_sharpe') }}</div>
    <div ref="subContainer" class="chart-sub" />

    <n-empty v-if="!series" :description="t('backtest.no_result')" style="padding: 48px 0;" />
  </n-card>
</template>

<style scoped>
.head-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  margin-bottom: 12px;
}
.hs-label {
  font-size: 11px;
  opacity: 0.6;
}
.hs-value {
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.chart-main {
  width: 100%;
  height: 300px;
}
.chart-sub {
  width: 100%;
  height: 120px;
}
.sub-title {
  font-size: 12px;
  opacity: 0.65;
  margin: 8px 0 4px;
  color: #f0b90b;
}
</style>
