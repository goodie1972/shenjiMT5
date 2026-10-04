<script setup lang="ts">
/**
 * BacktestKlineChart.vue — v7 K 线四联图（对齐 AM 的 K 线区）
 * 蜡烛图（涨红跌绿·中国习惯）+ 成交量副图 + MA20/MA60 叠加 + 买卖点标记（entry/exit）。
 * 数据来自后端 result.candles / result.trade_markers（time=Unix 秒 UTC）。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { createChart, ColorType, type UTCTimestamp, type IChartApi, type ISeriesApi, type SeriesMarker } from 'lightweight-charts'
import { useAppStore } from '@/stores/app'
import type { BacktestResult, BacktestCandle, BacktestMarker } from '@/types'

const props = defineProps<{ result: BacktestResult }>()
const { t } = useI18n()
const app = useAppStore()

// 中国习惯：涨红跌绿
const UP = '#f6465d'
const DOWN = '#0ecb81'
const GOLD = '#f0b90b'
const BUY = '#0ecb81'    // 买入标记（绿）
const SELL = '#f6465d'   // 卖出标记（红）
const MUTED = '#8b8f97'

const container = ref<HTMLDivElement | null>(null)
let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null
let volSeries: ISeriesApi<'Histogram'> | null = null
let ma20: ISeriesApi<'Line'> | null = null
let ma60: ISeriesApi<'Line'> | null = null
let resizeObs: ResizeObserver | null = null

const candles = computed<BacktestCandle[]>(() => props.result.candles || [])
const markers = computed<BacktestMarker[]>(() => props.result.trade_markers || [])

/** 简单移动平均 */
function sma(values: number[], n: number): Array<{ time: number; value: number }> {
  const out: Array<{ time: number; value: number }> = []
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= n) sum -= values[i - n]
    if (i >= n - 1) out.push({ time: candles.value[i].time, value: +(sum / n).toFixed(2) })
  }
  return out
}

function chartOptions(width: number, height: number) {
  const isDark = app.isDark
  return {
    layout: {
      background: { type: ColorType.Solid, color: isDark ? '#1a1d23' : '#ffffff' },
      textColor: isDark ? '#8b8f97' : '#555555',
    },
    grid: {
      vertLines: { color: isDark ? '#2d3139' : '#eef0f2' },
      horzLines: { color: isDark ? '#2d3139' : '#eef0f2' },
    },
    width, height,
    timeScale: { timeVisible: true, secondsVisible: false, borderColor: isDark ? '#2d3139' : '#d0d0d0' },
    rightPriceScale: { borderColor: isDark ? '#2d3139' : '#d0d0d0' },
    crosshair: { mode: 0 },
  }
}

/** 交易标记 → lightweight-charts markers（按时间升序） */
function buildMarkers(): SeriesMarker<UTCTimestamp>[] {
  const list = markers.value
    .map(m => ({
      time: m.time as UTCTimestamp,
      isBuy: (m.side || '').toUpperCase().startsWith('B'),
      isEntry: m.type === 'entry',
    }))
    .sort((a, b) => (a.time as number) - (b.time as number))
  return list.map(m => m.isEntry
    ? {
        time: m.time,
        position: m.isBuy ? ('belowBar' as const) : ('aboveBar' as const),
        color: m.isBuy ? BUY : SELL,
        shape: m.isBuy ? ('arrowUp' as const) : ('arrowDown' as const),
        text: m.isBuy ? t('backtest.kline_long') : t('backtest.kline_short'),
      }
    : {
        time: m.time,
        position: m.isBuy ? ('aboveBar' as const) : ('belowBar' as const),
        color: MUTED,
        shape: 'circle' as const,
        text: '',
      })
}

function render() {
  const data = candles.value
  if (!data.length || !container.value) return
  destroy()

  const w = container.value.clientWidth
  chart = createChart(container.value, chartOptions(w, 420))

  candleSeries = chart.addCandlestickSeries({
    upColor: UP, downColor: DOWN,
    borderUpColor: UP, borderDownColor: DOWN,
    wickUpColor: UP, wickDownColor: DOWN,
  })
  candleSeries.setData(
    data.map(c => ({
      time: c.time as UTCTimestamp,
      open: c.open, high: c.high, low: c.low, close: c.close,
    }))
  )

  // 成交量副图（叠加在价格区下方，scaleMargins 让出顶部空间）
  const closes = data.map(c => c.close)
  volSeries = chart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: 'vol',
  })
  chart.priceScale('vol').applyOptions({
    scaleMargins: { top: 0.82, bottom: 0 },
  })
  volSeries.setData(
    data.map(c => ({
      time: c.time as UTCTimestamp,
      value: c.volume,
      color: c.close >= c.open ? 'rgba(246,70,93,0.45)' : 'rgba(14,203,129,0.45)',
    }))
  )

  // MA 叠加
  ma20 = chart.addLineSeries({ color: GOLD, lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
  ma20.setData(sma(closes, 20))
  ma60 = chart.addLineSeries({ color: '#5b8def', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
  ma60.setData(sma(closes, 60))

  // 买卖点标记
  candleSeries.setMarkers(buildMarkers())

  // 注意：之前在 price=0 处画了虚线零轴，但 XAUUSD 价格在 $2000 左右，
  // 0 轴会让价格轴从 0 缩放到 2000+，蜡烛体被压缩成肉眼不可见的横线。
  // 已移除 price=0 零轴线，让图表自动缩放到实际价格范围。
}

function destroy() {
  chart?.remove(); chart = null
  candleSeries = null; volSeries = null; ma20 = null; ma60 = null
}

function onResize() {
  if (chart && container.value) chart.applyOptions({ width: container.value.clientWidth })
}

onMounted(() => {
  resizeObs = new ResizeObserver(onResize)
  if (container.value) resizeObs.observe(container.value)
})

onBeforeUnmount(() => {
  resizeObs?.disconnect()
  destroy()
})

// immediate: true —— 父组件以 v-if="result" 挂载，结果在挂载时已有值
watch(() => props.result, () => nextTick(render), { deep: false, immediate: true })
watch(() => app.isDark, () => nextTick(render))
</script>

<template>
  <n-card :title="t('backtest.kline_title')" size="small" class="bt-panel">
    <template #header-extra>
      <n-space :size="10" align="center">
        <span class="legend"><i class="dot" style="background:#f0b90b" />MA20</span>
        <span class="legend"><i class="dot" style="background:#5b8def" />MA60</span>
        <span class="legend"><i class="arrow" style="color:#0ecb81">▲</i>{{ t('backtest.kline_long') }}</span>
        <span class="legend"><i class="arrow" style="color:#f6465d">▼</i>{{ t('backtest.kline_short') }}</span>
      </n-space>
    </template>
    <div ref="container" class="chart-box" />
    <n-empty v-if="!candles.length" :description="t('backtest.no_result')" style="padding: 48px 0;" />
  </n-card>
</template>

<style scoped>
.chart-box {
  width: 100%;
  height: 420px;
}
.legend {
  font-size: 11px;
  opacity: 0.7;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.legend .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.legend .arrow {
  font-size: 11px;
  line-height: 1;
}
</style>
