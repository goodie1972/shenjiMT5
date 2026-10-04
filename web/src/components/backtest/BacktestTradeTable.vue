<script setup lang="ts">
/**
 * BacktestTradeTable.vue — AM 风格"整体明细"交易表
 * 全部 trades（v3 全字段：时间/方向/价格/持仓bar/盈亏/累计盈亏）。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { h } from 'vue'
import type { BacktestTrade } from '@/types'

const props = defineProps<{ trades: BacktestTrade[]; multiStrategy?: boolean }>()
const { t } = useI18n()

const PROFIT = '#0ecb81'
const LOSS = '#f6465d'

const cols = computed(() => {
  const list: any[] = [
    { title: '#', key: 'idx', width: 52, render: (_: any, i: number) => i + 1 },
    { title: t('backtest.entry_time'), key: 'entry_time', width: 150, ellipsis: { tooltip: true } },
    {
      title: t('backtest.direction'), key: 'direction', width: 64,
      render: (row: BacktestTrade) => row.direction === 'BUY'
        ? h('span', { style: { color: PROFIT, fontWeight: 600 } }, t('backtest.buy'))
        : h('span', { style: { color: LOSS, fontWeight: 600 } }, t('backtest.sell')),
    },
    { title: t('backtest.entry_price'), key: 'entry_price', width: 88 },
    { title: t('backtest.exit_price'), key: 'exit_price', width: 88 },
    {
      title: t('backtest.hold_bars'), key: 'hold_bars', width: 76,
      render: (row: BacktestTrade) => row.hold_bars ?? '—',
    },
    {
      title: t('backtest.pnl'), key: 'pnl', width: 96,
      // 必须返回 VNode（普通对象会被 Naive UI toString 成 [object Object]）
      render: (row: BacktestTrade) => h(
        'span',
        { style: { color: (row.pnl ?? 0) >= 0 ? PROFIT : LOSS, fontWeight: 600 } },
        `${(row.pnl ?? 0) >= 0 ? '+' : ''}$${(row.pnl ?? 0).toFixed(2)}`,
      ),
    },
    {
      title: t('backtest.cum_pnl'), key: 'cum_pnl', width: 100,
      render: (row: BacktestTrade) => row.cum_pnl != null
        ? `${row.cum_pnl >= 0 ? '+' : ''}$${row.cum_pnl.toFixed(2)}`
        : '—',
    },
  ]
  if (props.multiStrategy) {
    list.splice(1, 0, { title: t('backtest.strategy'), key: 'strategy', width: 110, ellipsis: { tooltip: true } })
  }
  return list
})

const data = computed(() => props.trades ?? [])
</script>

<template>
  <n-data-table :columns="cols" :data="data" :bordered="true" size="small"
                :max-height="420" :pagination="{ pageSize: 20, showSizePicker: true, pageSizes: [20, 50, 100] }"
                :scroll-x="760" />
</template>
