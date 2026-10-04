import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getTradeHistory } from '@/api/client'
import type { ClosedTrade } from '@/types'

export const useTradeStore = defineStore('trades', () => {
  const items = ref<ClosedTrade[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const total = ref(0)

  // 30s TTL：同一组参数 30 秒内不重复请求（不同参数仍然实时拉取）
  let lastFetchAt = 0
  let lastFetchKey = ''
  async function fetch(limit = 100, offset = 0, mode?: string) {
    const key = `${limit}|${offset}|${mode || ''}`
    if (key === lastFetchKey && Date.now() - lastFetchAt < 30_000) return
    lastFetchKey = key
    lastFetchAt = Date.now()
    loading.value = true
    error.value = null
    try {
      const result = await getTradeHistory(limit, offset, mode)
      items.value = result.trades
      total.value = result.total
    } catch (e: any) {
      error.value = e?.message || '获取历史成交失败'
    } finally {
      loading.value = false
    }
  }

  function $reset() {
    items.value = []
    loading.value = false
    error.value = null
    total.value = 0
  }

  return { items, loading, error, total, fetch, $reset }
})
