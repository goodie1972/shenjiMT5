<script setup lang="ts">
/**
 * BacktestInterpret.vue — 解读区（双轨）
 * 1) 规则化解读：基于汇总统计生成人话结论（收益档位/盈亏结构/回撤/夏普/数据可靠性）——始终可用
 * 2) AI 解读：点击按钮调用已激活的 LLM Provider（POST /backtest/interpret/{job_id}）生成中文诊断
 *    LLM 未配置或调用失败时保留规则模板，并显式提示失败原因。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useBacktestStore } from '@/stores/backtest'
import type { BacktestResult } from '@/types'

const props = defineProps<{ result: BacktestResult; jobId?: string | null }>()
const { t } = useI18n()
const backtest = useBacktestStore()

const first = computed(() => {
  const by = props.result.by_strategy || {}
  const name = Object.keys(by)[0]
  return name ? by[name] : null
})

const bullets = computed(() => {
  const out: string[] = []
  const ret = props.result.total_return_pct ?? 0
  const wr = props.result.win_rate ?? 0
  const plr = first.value?.profit_loss_ratio ?? null
  const mdd = props.result.max_drawdown ?? 0
  const sharpe = first.value?.sharpe ?? props.result.sharpe_ratio ?? 0
  const hold = first.value?.avg_hold_bars ?? null

  // 1. 收益档位
  if (ret >= 30) out.push(t('backtest.interpret_return_strong', { v: ret.toFixed(1) }))
  else if (ret >= 10) out.push(t('backtest.interpret_return_mid', { v: ret.toFixed(1) }))
  else if (ret >= 0) out.push(t('backtest.interpret_return_weak', { v: ret.toFixed(1) }))
  else out.push(t('backtest.interpret_return_loss', { v: Math.abs(ret).toFixed(1) }))

  // 2. 盈亏结构
  if (plr != null) {
    let style = t('backtest.interpret_style_plain')
    if (wr >= 55) style = t('backtest.interpret_style_high_wr')
    else if (plr >= 1.8) style = t('backtest.interpret_style_low_wr_plr')
    out.push(t('backtest.interpret_wr', { wr: wr.toFixed(1), plr: plr.toFixed(2), style }))
  }

  // 3. 回撤
  if (mdd < 10) out.push(t('backtest.interpret_mdd_low', { v: mdd.toFixed(1) }))
  else if (mdd < 25) out.push(t('backtest.interpret_mdd_mid', { v: mdd.toFixed(1) }))
  else out.push(t('backtest.interpret_mdd_high', { v: mdd.toFixed(1) }))

  // 4. 夏普档位
  if (sharpe >= 1.5) out.push(t('backtest.interpret_sharpe_good', { v: sharpe.toFixed(2) }))
  else if (sharpe >= 0.5) out.push(t('backtest.interpret_sharpe_ok', { v: sharpe.toFixed(2) }))
  else out.push(t('backtest.interpret_sharpe_bad', { v: sharpe.toFixed(2) }))

  // 5. 持仓节奏
  if (hold != null && hold > 0) out.push(t('backtest.interpret_hold', { v: hold }))

  // 6. 数据可靠性
  const src = props.result.data_source as any
  if (src?.source === 'simulated') {
    out.push(t('backtest.interpret_simulated'))
  }
  return out
})

/** AI 解读按行拆分（LLM 常返回 1. 2. 或 - 列表） */
const aiLines = computed(() => {
  const txt = backtest.aiText
  if (!txt) return []
  return txt.split('\n')
    .map(s => s.replace(/^\s*(\d+[.、)]|[-*•])\s*/, '').trim())
    .filter(s => s.length > 0)
})
</script>

<template>
  <n-card size="small">
    <template #header>
      <div class="hd">
        <span>{{ t('backtest.interpret_title') }}</span>
        <n-space :size="8" align="center">
          <n-tag v-if="backtest.aiText" size="tiny" type="success" :bordered="false">
            {{ t('backtest.ai_by', { provider: backtest.aiMeta?.provider || 'LLM', model: backtest.aiMeta?.model || '' }) }}
          </n-tag>
          <n-tag v-else size="tiny" :bordered="false">{{ t('backtest.rule_interpret') }}</n-tag>
        </n-space>
      </div>
    </template>
    <template #header-extra>
      <n-button size="tiny" secondary type="primary" :loading="backtest.aiLoading"
                :disabled="!jobId || backtest.aiLoading" @click="backtest.requestAiInterpret()">
        {{ backtest.aiLoading ? t('backtest.ai_interpret_loading') : t('backtest.ai_interpret_btn') }}
      </n-button>
    </template>

    <!-- AI 解读优先 -->
    <ul v-if="aiLines.length" class="interpret-list">
      <li v-for="(b, i) in aiLines" :key="'ai' + i" class="interpret-item ai">{{ b }}</li>
    </ul>
    <!-- 否则规则化模板 -->
    <ul v-else class="interpret-list">
      <li v-for="(b, i) in bullets" :key="i" class="interpret-item">{{ b }}</li>
    </ul>

    <n-alert v-if="backtest.aiError" type="warning" :bordered="false" style="margin-top: 10px;">
      {{ t('backtest.ai_interpret_failed', { err: backtest.aiError }) }}
    </n-alert>
  </n-card>
</template>

<style scoped>
.interpret-list {
  margin: 0;
  padding-left: 4px;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.interpret-item {
  position: relative;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.6;
}
.interpret-item::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 8px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f0b90b;
}
.interpret-item.ai::before {
  background: #0ecb81;
}
.hd {
  display: flex;
  align-items: center;
  gap: 10px;
}
</style>
