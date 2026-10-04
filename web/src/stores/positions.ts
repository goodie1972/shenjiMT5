import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getPositions, closePosition, modifyPosition } from '@/api/client'
import type { Position } from '@/types'

export const usePositionStore = defineStore('positions', () => {
  const items = ref<Position[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  // 关闭中的 ticket 集合：WS 推送持仓时过滤掉，避免平仓确认延迟期间旧单被重新加回
  const closingTickets = ref<Set<string>>(new Set())

  const totalProfit = computed(() => items.value.reduce((s, p) => s + p.profit, 0))
  const longCount = computed(() => items.value.filter(p => p.order_type === 'OP_BUY' || p.order_type === 'BUY').length)
  const shortCount = computed(() => items.value.filter(p => p.order_type === 'OP_SELL' || p.order_type === 'SELL').length)

  // 30s TTL：避免切页重复请求同一份持仓数据
  let lastFetchAt = 0
  async function fetch(force = false) {
    if (!force && Date.now() - lastFetchAt < 30_000) return
    lastFetchAt = Date.now()
    loading.value = true
    error.value = null
    try {
      items.value = await getPositions()
    } catch (e: any) {
      error.value = e?.message || '获取持仓失败'
    } finally {
      loading.value = false
    }
  }

  function updateFromWs(data: Position[]) {
    const set = closingTickets.value
    items.value = set.size ? data.filter(p => !set.has(String(p.ticket))) : data
    error.value = null
  }

  async function close(ticket: number) {
    const key = String(ticket)
    const markClosing = () => {
      const s = new Set(closingTickets.value)
      s.add(key)
      closingTickets.value = s
    }
    const unmarkClosing = () => {
      const s = new Set(closingTickets.value)
      s.delete(key)
      closingTickets.value = s
    }
    try {
      await closePosition(ticket)
      // 标记关闭中 + 本地立即隐藏；WS 推送会据此过滤，避免确认延迟期间旧单被加回
      markClosing()
      items.value = items.value.filter(p => String(p.ticket) !== key)
      // 确认式轮询：后端平仓经券商确认有延迟，缓存可能短暂仍含该单。
      // 轮询拉取最新持仓，服务端确认平仓（该 ticket 消失）后才采用最新列表，
      // 否则保持本地隐藏，杜绝"平仓后仍在列表 / 需手动刷新"的错觉。
      // 8 轮 × 3s 单次超时 + 200ms 间隔 → 总预算约 25s 封顶（防止确认对话框的全屏遮罩悬挂数分钟）
      for (let i = 0; i < 8; i++) {
        try {
          const latest = await getPositions(3000)
          if (!latest.some(p => String(p.ticket) === key)) {
            items.value = latest
            break
          }
        } catch { /* 拉取失败保持隐藏，下一轮重试 */ }
        await new Promise(r => setTimeout(r, 200))
      }
      unmarkClosing()
    } catch (e: any) {
      const status = e?.response?.status
      if (status === 404) {
        // 订单已不存在：本地同步移除 + 抛出标记错误，由调用方提示友好文案
        unmarkClosing()
        items.value = items.value.filter(p => String(p.ticket) !== key)
        throw Object.assign(new Error('NOT_FOUND'), { notFound: true })
      }
      // 网络超时：平仓命令可能已被 MT4 执行（后端仍在跑），轮询确认再下结论
      const isTimeout = e?.code === 'ECONNABORTED' || /timeout|timed ?out/i.test(e?.message || '')
      if (isTimeout) {
        try {
          const latest = await getPositions()
          if (!latest.some(p => String(p.ticket) === key)) {
            unmarkClosing()
            items.value = latest
            throw Object.assign(new Error('TIMEOUT_BUT_CLOSED'), { timeoutButClosed: true, ticket })
          }
        } catch { /* 忽略刷新失败 */ }
      }
      unmarkClosing()
      throw e
    }
  }

  async function modify(ticket: number, sl?: number, tp?: number) {
    await modifyPosition(ticket, sl, tp)
    await fetch()
  }

  return { items, loading, error, totalProfit, longCount, shortCount, fetch, updateFromWs, close, modify }
})
