<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import StrategyPool from '@/components/strategy/StrategyPool.vue'

const { t } = useI18n()
</script>

<template>
  <n-space vertical size="large">
    <n-h2>{{ t('strategy.title') }}</n-h2>
    <StrategyPool />
  </n-space>
</template>
