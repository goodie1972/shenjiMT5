import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getAccount } from '@/api/client'
import type { AccountInfo } from '@/types'

export const useAccountStore = defineStore('account', () => {
  const info = ref<AccountInfo | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 30s TTL：避免切页重复请求账户信息
  let lastFetchAt = 0
  async function fetch(force = false) {
    if (!force && Date.now() - lastFetchAt < 30_000) return
    lastFetchAt = Date.now()
    loading.value = true
    error.value = null
    try {
      info.value = await getAccount()
    } catch (e: any) {
      error.value = e?.message || '获取账户信息失败'
    } finally {
      loading.value = false
    }
  }

  function updateFromWs(data: AccountInfo) {
    info.value = data
    error.value = null  // WebSocket 数据到达说明连接正常，清除之前的错误
  }

  return { info, loading, error, fetch, updateFromWs }
})
