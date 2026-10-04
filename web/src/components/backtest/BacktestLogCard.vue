<script setup lang="ts">
/**
 * BacktestLogCard.vue — AM 风格"回测日志"卡
 * 运行中实时尾随 phase/log_tail（store 轮询更新），终端风深色底 + 自动滚底。
 */
import { ref, watch, nextTick, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ logs: string[]; phase: string; running: boolean }>()
const { t } = useI18n()

const box = ref<HTMLDivElement | null>(null)

const phaseInfo = computed(() => {
  switch (props.phase) {
    case 'queued': return { label: t('backtest.phase_queued'), type: 'default' as const }
    case 'data': return { label: t('backtest.phase_data'), type: 'info' as const }
    case 'compute': return { label: t('backtest.phase_compute'), type: 'info' as const }
    case 'stats': return { label: t('backtest.phase_stats'), type: 'info' as const }
    case 'done': return { label: t('backtest.phase_done'), type: 'success' as const }
    case 'failed': return { label: t('backtest.phase_failed'), type: 'error' as const }
    default: return null
  }
})

watch(() => props.logs, async () => {
  await nextTick()
  if (box.value) box.value.scrollTop = box.value.scrollHeight
}, { deep: true })
</script>

<template>
  <n-card size="small" :title="t('backtest.log_title')" class="log-card">
    <template #header-extra>
      <n-space :size="8" align="center">
        <n-tag v-if="phaseInfo" size="small" :type="phaseInfo.type" :bordered="false">
          {{ phaseInfo.label }}
        </n-tag>
        <n-spin v-if="running" :size="14" />
      </n-space>
    </template>
    <div ref="box" class="log-box">
      <div v-if="!logs.length" class="log-empty">{{ t('backtest.log_empty') }}</div>
      <div v-for="(ln, i) in logs" :key="i" class="log-line" :class="{ 'log-warn': ln.includes('警告'), 'log-err': ln.includes('失败') }">
        {{ ln }}
      </div>
    </div>
  </n-card>
</template>

<style scoped>
.log-box {
  height: 420px;
  overflow-y: auto;
  background: #14161a;
  border-radius: 6px;
  padding: 10px 12px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.7;
  color: #a8b3c5;
}
.log-line {
  white-space: pre-wrap;
  word-break: break-all;
}
.log-warn { color: #f0b90b; }
.log-err { color: #f6465d; }
.log-empty {
  opacity: 0.5;
  text-align: center;
  padding-top: 180px;
}
</style>
