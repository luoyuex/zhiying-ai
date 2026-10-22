/**
 * 从 CSS :root 读取 CSS 变量的值，供 Canvas/SVG 渲染使用。
 * 因为 Canvas 无法读取 CSS 变量，必须先读出来才能传给图表库。
 */
export function readToken(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}
