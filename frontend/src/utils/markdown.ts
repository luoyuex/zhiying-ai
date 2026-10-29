import DOMPurify from 'dompurify'
import { marked } from 'marked'

marked.setOptions({ gfm: true, breaks: true })

let hookReady = false

/** 外链统一新窗口打开，避免 AI 输出里的链接把应用跳走。 */
function ensureLinkHook(): void {
  if (hookReady) return
  hookReady = true
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.tagName === 'A') {
      node.setAttribute('target', '_blank')
      node.setAttribute('rel', 'noopener noreferrer')
    }
  })
}

/**
 * 报告正文常以 `# xxx分析报告` / `## 行业板块分析报告` 开头，
 * 外面的卡片已经有标题，去掉这层重复。
 */
function stripLeadingTitle(source: string): string {
  const match = source.match(/^(#{1,2})\s+([^\n]{1,40})\n+([\s\S]*)$/)
  if (!match) return source
  const isReportTitle = match[1] === '#' || /报告$/.test(match[2].trim())
  return isReportTitle ? match[3].trim() : source
}

/** 把 AI 报告里的 Markdown 渲染成可直接插入的安全 HTML。 */
export function renderMarkdown(text?: string | null): string {
  const source = (text ?? '').trim()
  if (!source) return ''
  ensureLinkHook()
  const html = marked.parse(stripLeadingTitle(source), { async: false })
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    ADD_ATTR: ['target', 'rel'],
  })
}
