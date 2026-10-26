import { ref } from 'vue'

/** 价位提醒变更信号：自选卡、汇总面板与报告页共享，任一处修改后其它处刷新。 */
const version = ref(0)

export function notifyPriceAlertsChanged(): void {
  version.value += 1
}

export function usePriceAlertsVersion() {
  return version
}
