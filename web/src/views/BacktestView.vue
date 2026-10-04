<script setup lang="ts">
/**
 * BacktestView.vue — 回测中心（对齐 AM 的分区与节奏，配色沿用本项目金色主题）
 * ① 启动回测卡 → ② 六指标卡（3 列 × 2 行）→ ③ 资金曲线(3/5) + 回测日志(2/5) 并排
 * → ④ 整体明细（全宽）→ ⑤ AI 解读 → ⑥ 回测记录（折叠）。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import BacktestPanel from '@/components/strategy/BacktestPanel.vue'
import BacktestStatCards from '@/components/backtest/BacktestStatCards.vue'
import BacktestTradeTable from '@/components/backtest/BacktestTradeTable.vue'
import BacktestLogCard from '@/components/backtest/BacktestLogCard.vue'
import BacktestEquityChart from '@/components/backtest/BacktestEquityChart.vue'
import BacktestKlineChart from '@/components/backtest/BacktestKlineChart.vue'
import BacktestTopTrades from '@/components/backtest/BacktestTopTrades.vue'
import BacktestInterpret from '@/components/backtest/BacktestInterpret.vue'
import BacktestResults from '@/components/strategy/BacktestResults.vue'
import { useBacktestStore } from '@/stores/backtest'

const { t } = useI18n()
const backtest = useBacktestStore()

const result = computed(() => backtest.result)
const multiStrategy = computed(() =>
  Object.keys(result.value?.by_strategy ?? {}).length > 1)

/** v7：导出回测结果为 JSON 文件 */
function exportJson() {
  if (!result.value) return
  const blob = new Blob([JSON.stringify(result.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  const tf = result.value.timeframe || 'XAUUSD'
  a.href = url
  a.download = `backtest_${tf}_${result.value.start_date || ''}_${result.value.end_date || ''}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="bt-view">
    <n-h2 class="bt-page-title">{{ t('backtest.center_title') }}</n-h2>

    <!-- 数据源状态条 -->
    <n-alert type="info" :bordered="false" class="bt-alert">
      {{ t('backtest.datasource_hint') }}
    </n-alert>

    <!-- ① 启动回测（含策略选择 / 组合指标） -->
    <BacktestPanel />

    <!-- ② 六指标卡（3 列 × 2 行） -->
    <BacktestStatCards v-if="result" :result="result" />

    <!-- ③ 资金曲线 3 : 日志 2 -->
    <n-grid v-if="result" cols="5" :x-gap="22">
      <n-gi span="3">
        <BacktestEquityChart :result="result" />
      </n-gi>
      <n-gi span="2">
        <BacktestLogCard :logs="backtest.logTail" :phase="backtest.phase" :running="backtest.loading" />
      </n-gi>
    </n-grid>

    <!-- 回测运行中且尚无结果时，单独展示日志窗口 -->
    <BacktestLogCard v-if="!result && backtest.loading" :logs="backtest.logTail" :phase="backtest.phase" :running="true" />

    <!-- ③-b v7：K 线四联图（蜡烛 + 成交量 + MA + 买卖点） -->
    <BacktestKlineChart v-if="result" :result="result" />

    <!-- ④ 整体明细 -->
    <n-card v-if="result" :title="t('backtest.detail_title')" size="small" class="bt-panel">
      <template #header-extra>
        <n-button size="small" tertiary @click="exportJson">{{ t('backtest.export_json') }}</n-button>
      </template>
      <BacktestTradeTable :trades="result.trades" :multi-strategy="multiStrategy" />
    </n-card>

    <!-- ④-b v7：Top 5 盈亏单 -->
    <BacktestTopTrades v-if="result" :result="result" />

    <!-- ⑤ AI 解读 -->
    <BacktestInterpret v-if="result" :result="result" :job-id="backtest.jobId" />

    <!-- 空状态引导（无结果时） -->
    <n-card v-if="!result" size="small" class="bt-panel">
      <n-empty :description="t('backtest.empty_guide')" style="padding: 56px 0;" />
    </n-card>

    <!-- ⑥ 回测记录（历史 job 列表） -->
    <n-collapse>
      <n-collapse-item :title="t('backtest.records_title')" name="records">
        <BacktestResults />
      </n-collapse-item>
    </n-collapse>
  </div>
</template>

<style scoped>
/* 对齐 AM 的区块节奏：面板间距 22px、标题 0.82rem 大写 + 左侧竖条 */
.bt-view {
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.bt-page-title {
  margin: 0 0 4px;
  font-size: 1.35rem;
  font-weight: 600;
}
.bt-alert {
  margin: 0;
}
.bt-view :deep(.n-card) {
  border-radius: 12px;
}
.bt-view :deep(.n-card-header__main) {
  font-size: 0.82rem;
  font-weight: 600;
  letter-spacing: 0.08em;
}
.bt-panel {
  border-radius: 12px;
}
</style>
