<script setup lang="ts">
/**
 * BacktestTopTrades.vue — v7 Top 5 盈亏单
 * 从 result.trades 取 PnL 最高/最低的 5 笔（多策略时合并计算），左右两栏展示。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { BacktestResult, BacktestTrade } from '@/types'

const props = defineProps<{ result: BacktestResult }>()
const { t } = useI18n()

const PROFIT = '#0ecb81'
const LOSS = '#f6465d'

const topWinners = computed<BacktestTrade[]>(() =>
  [...(props.result.trades || [])].sort((a, b) => b.pnl - a.pnl).slice(0, 5))
const topLosers = computed<BacktestTrade[]>(() =>
  [...(props.result.trades || [])].sort((a, b) => a.pnl - b.pnl).slice(0, 5))

function fmt(v: number): string {
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function pnlColor(v: number): string {
  return v >= 0 ? PROFIT : LOSS
}
</script>

<template>
  <n-card :title="t('backtest.top_trades_title')" size="small" class="bt-panel">
    <n-grid :cols="2" :x-gap="18">
      <n-gi>
        <div class="col-title win">{{ t('backtest.top_winners') }}</div>
        <div v-for="(tr, i) in topWinners" :key="'w' + i" class="row">
          <span class="idx">{{ i + 1 }}</span>
          <span class="strat">{{ tr.strategy }}</span>
          <span class="dir" :class="tr.direction === 'BUY' ? 'long' : 'short'">
            {{ tr.direction === 'BUY' ? t('backtest.buy') : t('backtest.sell') }}
          </span>
          <span class="pnl" :style="{ color: pnlColor(tr.pnl) }">{{ fmt(tr.pnl) }}</span>
          <span class="meta">{{ tr.hold_bars ?? '—' }} bar</span>
        </div>
        <n-empty v-if="!topWinners.length" :description="t('backtest.no_result')" style="padding: 18px 0;" />
      </n-gi>
      <n-gi>
        <div class="col-title loss">{{ t('backtest.top_losers') }}</div>
        <div v-for="(tr, i) in topLosers" :key="'l' + i" class="row">
          <span class="idx">{{ i + 1 }}</span>
          <span class="strat">{{ tr.strategy }}</span>
          <span class="dir" :class="tr.direction === 'BUY' ? 'long' : 'short'">
            {{ tr.direction === 'BUY' ? t('backtest.buy') : t('backtest.sell') }}
          </span>
          <span class="pnl" :style="{ color: pnlColor(tr.pnl) }">{{ fmt(tr.pnl) }}</span>
          <span class="meta">{{ tr.hold_bars ?? '—' }} bar</span>
        </div>
        <n-empty v-if="!topLosers.length" :description="t('backtest.no_result')" style="padding: 18px 0;" />
      </n-gi>
    </n-grid>
  </n-card>
</template>

<style scoped>
.col-title {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  margin-bottom: 10px;
  text-transform: uppercase;
}
.col-title.win { color: #0ecb81; }
.col-title.loss { color: #f6465d; }
.row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  border-bottom: 1px solid var(--n-border-color, rgba(128, 128, 128, 0.14));
  font-size: 12px;
}
.idx {
  width: 18px;
  opacity: 0.5;
  text-align: center;
}
.strat {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dir {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
}
.dir.long { color: #0ecb81; background: rgba(14, 203, 129, 0.12); }
.dir.short { color: #f6465d; background: rgba(246, 70, 93, 0.12); }
.pnl {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  min-width: 78px;
  text-align: right;
}
.meta {
  opacity: 0.5;
  min-width: 48px;
  text-align: right;
}
</style>
