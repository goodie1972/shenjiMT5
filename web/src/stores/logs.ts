import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getLogs } from '@/api/client'
import type { LogEntry } from '@/types'

export const useLogStore = defineStore('logs', () => {
  const entries = ref<LogEntry[]>([])
  const filterLevel = ref<string | null>(null)
  const maxEntries = 500
  let idCounter = 0

  const filteredEntries = computed(() => {
    if (!filterLevel.value) return entries.value
    const levels = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3 }
    const min = levels[filterLevel.value as keyof typeof levels] ?? 0
    return entries.value.filter(e => (levels[e.level as keyof typeof levels] ?? 0) >= min)
  })

  function append(entry: LogEntry) {
    // 统一字段名：WebSocket 推送的是 time，数据库返回的是 timestamp
    const normalized = { ...entry, timestamp: (entry as any).time || entry.timestamp }
    entries.value.unshift({ ...normalized, _id: ++idCounter })  // 新日志在最前
    if (entries.value.length > maxEntries) {
      entries.value.pop()
    }
  }

  async function fetchHistory(level?: string, limit = 100) {
    try {
      const logs = await getLogs(level, limit)
      // L-12：原 Set 去重按 timestamp+message 全等 → 同秒同内容的多条合法日志
      // 会被误去重。改为「配额消费」：统计现有各键条数，DB 每行先消费一条
      // 已有配额（跳过），配额之外的才加入——保留同键多条的多样性。
      const avail = new Map<string, number>()
      for (const e of entries.value) {
        const k = e.timestamp + e.message
        avail.set(k, (avail.get(k) || 0) + 1)
      }
      for (const log of logs) {
        const k = log.timestamp + log.message
        const n = avail.get(k) || 0
        if (n > 0) {
          avail.set(k, n - 1)
          continue
        }
        entries.value.unshift({ ...log, _id: ++idCounter })  // 新日志在最前
      }
      if (entries.value.length > maxEntries) {
        entries.value.splice(maxEntries)
      }
    } catch { /* ignore */ }
  }

  function clear() {
    entries.value = []
  }

  return { entries, filterLevel, filteredEntries, append, fetchHistory, clear }
})
