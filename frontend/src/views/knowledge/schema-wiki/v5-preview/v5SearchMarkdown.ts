import { marked } from 'marked'

import { sanitizeMarkdownHTML } from '../../../../utils/security.ts'

let markedConfigured = false

function configureMarked(): void {
  if (markedConfigured) return
  marked.use({ gfm: true, breaks: true })
  markedConfigured = true
}

/** Render model Markdown with the same sanitizer used by the main chat UI. */
export function renderV5SearchMarkdown(markdown: string, streaming = false): string {
  if (!markdown.trim()) return ''
  configureMarked()
  // Avoid showing a dangling list marker while the final stream chunk is pending.
  const stableText = streaming
    ? markdown.replace(/(^|\n)[ \t]*(?:[-*+]|\d+[.)])[ \t]*$/u, '$1')
    : markdown
  const html = marked.parse(stableText, { async: false }) as string
  return sanitizeMarkdownHTML(html)
}
