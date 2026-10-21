import { computed, onUnmounted, ref } from 'vue'

export function useCountdown() {
  const remaining = ref(0)
  let timer: ReturnType<typeof setInterval> | undefined

  function stop(): void {
    if (timer !== undefined) {
      clearInterval(timer)
      timer = undefined
    }
    remaining.value = 0
  }

  function start(seconds: number): void {
    stop()
    remaining.value = Math.max(Math.floor(seconds), 0)
    if (remaining.value === 0) return
    timer = setInterval(() => {
      remaining.value -= 1
      if (remaining.value <= 0) stop()
    }, 1000)
  }

  onUnmounted(stop)

  return {
    remaining,
    running: computed(() => remaining.value > 0),
    start,
    stop,
  }
}
