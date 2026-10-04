/**
 * Route prefetch utility — 预加载所有懒加载路由的 chunk
 * 在 AppShell 挂载后、浏览器空闲时调用（requestIdleCallback + setTimeout 兜底）
 * 目的：消除导航切换时的加载转圈（route chunk + 首挂 fetch 并行 → 体感秒开）
 */
import router from '@/router'

// 从 router 配置提取所有动态 import() 的路由组件
const routeComponents = router.getRoutes()
  .filter((r) => typeof r.component === 'function')
  .map((r) => r.component as () => Promise<any>)

let prefetched = false
let prefetchPromise: Promise<void> | null = null

/**
 * 预取所有路由 chunk
 * @returns Promise<void> —— 可 await 也可 fire-and-forget
 */
export async function prefetchAllRoutes(): Promise<void> {
  if (prefetched || prefetchPromise) return prefetchPromise

  prefetchPromise = (async () => {
    // 并发预取所有 chunk（不阻塞、不求全序）
    await Promise.allSettled(routeComponents.map((importFn) => importFn()))
    prefetched = true
  })()

  return prefetchPromise
}

/**
 * 在浏览器空闲期触发预取（不抢首屏资源）
 * - requestIdleCallback：现代浏览器首选
 * - setTimeout 1.5s 兜底：Safari/旧内核或长任务占满主线程时
 */
export function schedulePrefetch(): void {
  if (prefetched) return

  const doPrefetch = () => {
    // 再次检查，避免重复
    if (!prefetched) {
      prefetchAllRoutes()
    }
  }

  if ('requestIdleCallback' in window) {
    // @ts-ignore — requestIdleCallback 在 lib.dom.d.ts 可能缺失
    requestIdleCallback(doPrefetch, { timeout: 2000 })
  } else {
    setTimeout(doPrefetch, 1500)
  }
}

/**
 * 预热高频 store（可选，视各 view 首挂依赖而定）
 * 在 AppShell onMounted 中调用，与 schedulePrefetch 并行
 */
export async function warmupStores(): Promise<void> {
  // 这里不直接 import store（避免循环依赖），由调用方决定预热哪些
  // 示例：
  // const { usePriceStore } = await import('@/stores/prices')
  // const { useAccountStore } = await import('@/stores/account')
  // const { usePositionStore } = await import('@/stores/positions')
  // await Promise.allSettled([usePriceStore().fetch(), useAccountStore().fetch(), usePositionStore().fetch()])
}