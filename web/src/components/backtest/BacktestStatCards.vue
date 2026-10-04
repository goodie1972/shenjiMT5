<script setup lang="ts">
/**
 * BacktestStatCards.vue — AM 风格六指标卡
 * 总收益(带 sparkline) / Sharpe(带 sparkline) / Sortino / 盈亏比 / 交易数 / 胜率
 * 统计取 by_strategy 第一策略的 v3 扩展字段（与后端 summary 口径一致）。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { BacktestResult } from '@/types'

const props = defineProps<{ result: BacktestResult }>()
const { t } = useI18n()

const PROFIT = '#0ecb81'
const LOSS = '#f6465d'
const GOLD = '#f0b90b'

const first = computed(() => {
  const by = props.result.by_strategy || {}
  const name = Object.keys(by)[0]
  return name ? by[name] : null
})

const returnPct = computed(() => props.result.total_return_pct ?? 0)
const returnColor = computed(() => returnPct.value >= 0 ? PROFIT : LOSS)
const sharpeVal = computed(() => first.value?.sharpe ?? props.result.sharpe_ratio ?? 0)
const sortinoVal = computed(() => first.value?.sortino ?? props.result.sortino ?? null)
const plrVal = computed(() => first.value?.profit_loss_ratio ?? null)
const avgHold = computed(() => first.value?.avg_hold_bars ?? null)

/** 序列抽样（等距） */
function sample<T>(arr: T[], n: number): T[] {
  if (arr.length <= n) return arr
  const step = arr.length / n
  return Array.from({ length: n }, (_, i) => arr[Math.floor(i * step)])
}

/** sparkline SVG path（null 过滤 + 抽样 80 点） */
function sparkPath(raw: Array<number | null> | undefined, w = 110, h = 32): string {
  if (!raw) return ''
  const vals = raw.filter((v): v is number => v != null && isFinite(v))
  if (vals.length < 2) return ''
  const s = sample(vals, 80)
  const min = Math.min(...s)
  const max = Math.max(...s)
  const span = max - min || 1
  const step = w / (s.length - 1)
  return s.map((v, i) =>
    `${i ? 'L' : 'M'}${(i * step).toFixed(1)},${(h - 2 - ((v - min) / span) * (h - 4)).toFixed(1)}`
  ).join(' ')
}

const retSpark = computed(() => sparkPath(first.value?.series?.equity))
const retSparkColor = computed(() => returnPct.value >= 0 ? PROFIT : LOSS)
const sharpeSpark = computed(() => sparkPath(first.value?.series?.rolling_sharpe, 110, 32))
</script>

<template>
  <!-- 桌面端固定 3 列 × 2 行，小屏 1 列 -->
  <n-grid :x-gap="14" :y-gap="14" responsive="screen" cols="3">
    <n-gi>
      <n-card size="small">
        <div class="stat-label">{{ t('backtest.stat_total_return') }}</div>
        <div class="stat-value" :style="{ color: returnColor }">
          {{ returnPct >= 0 ? '+' : '' }}{{ returnPct.toFixed(2) }}%
        </div>
        <svg v-if="retSpark" class="spark" viewBox="0 0 110 32" preserveAspectRatio="none">
          <path :d="retSpark" fill="none" :stroke="retSparkColor" stroke-width="1.5" />
        </svg>
      </n-card>
    </n-gi>
    <n-gi>
      <n-card size="small">
        <div class="stat-label">{{ t('backtest.stat_sharpe') }}</div>
        <div class="stat-value" :style="{ color: sharpeVal >= 1 ? PROFIT : undefined }">
          {{ sharpeVal.toFixed(2) }}
        </div>
        <svg v-if="sharpeSpark" class="spark" viewBox="0 0 110 32" preserveAspectRatio="none">
          <path :d="sharpeSpark" fill="none" :stroke="GOLD" stroke-width="1.5" />
        </svg>
      </n-card>
    </n-gi>
    <n-gi>
      <n-card size="small">
        <div class="stat-label">{{ t('backtest.stat_sortino') }}</div>
        <div class="stat-value">{{ sortinoVal != null ? sortinoVal.toFixed(2) : '—' }}</div>
      </n-card>
    </n-gi>
    <n-gi>
      <n-card size="small">
        <div class="stat-label">{{ t('backtest.stat_plr') }}</div>
        <div class="stat-value">{{ plrVal != null ? plrVal.toFixed(2) : '—' }}</div>
      </n-card>
    </n-gi>
    <n-gi>
      <n-card size="small">
        <div class="stat-label">{{ t('backtest.stat_trades') }}</div>
        <div class="stat-value">{{ result.total_trades }}</div>
        <div v-if="avgHold != null" class="stat-sub">
          {{ t('backtest.avg_hold') }} {{ avgHold }} bar
        </div>
      </n-card>
    </n-gi>
    <n-gi>
      <n-card size="small">
        <div class="stat-label">{{ t('backtest.stat_winrate') }}</div>
        <div class="stat-value">{{ result.win_rate.toFixed(1) }}%</div>
        <div class="winbar">
          <div class="winbar-fill" :style="{ width: Math.min(100, result.win_rate) + '%' }" />
        </div>
      </n-card>
    </n-gi>
  </n-grid>
</template>

<style scoped>
/* 对齐 AM：卡片 gap 14px、内边距 16/16/14、label 0.7rem 大写、value 1.5rem 等宽数字 */
:deep(.n-card) {
  border-radius: 12px;
}
:deep(.n-card__content) {
  padding: 16px 16px 14px !important;
}
.stat-label {
  font-size: 0.7rem;
  opacity: 0.65;
  margin-bottom: 8px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.stat-value {
  font-size: 1.5rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.stat-sub {
  font-size: 0.72rem;
  opacity: 0.55;
  margin-top: 4px;
}
.spark {
  width: 100%;
  height: 32px;
  margin-top: 4px;
  display: block;
}
.winbar {
  height: 4px;
  border-radius: 2px;
  background: rgba(128, 128, 128, 0.2);
  margin-top: 6px;
  overflow: hidden;
}
.winbar-fill {
  height: 100%;
  background: #0ecb81;
  border-radius: 2px;
}
</style>
