// @vitest-environment happy-dom

import { describe, expect, it, vi } from 'vitest'

vi.mock('../../../../utils/security.ts', () => ({
  sanitizeMarkdownHTML: (html: string) => html.replace(/<script[\s\S]*?<\/script>/gi, ''),
}))

import { renderV5SearchMarkdown } from './v5SearchMarkdown.ts'

describe('renderV5SearchMarkdown', () => {
  it('renders GFM tables, lists, and headings', () => {
    const html = renderV5SearchMarkdown([
      '# 保障对比',
      '',
      '| 产品 | 等待期 |',
      '| --- | --- |',
      '| e生保 | 30天 |',
      '',
      '- 有效',
      '- 待核对',
    ].join('\n'))

    expect(html).toContain('<table>')
    expect(html).toContain('<th>产品</th>')
    expect(html).toContain('<td>30天</td>')
    expect(html).toContain('<ul>')
    expect(html).toContain('<h1>保障对比</h1>')
  })

  it('sanitizes unsafe model output', () => {
    const html = renderV5SearchMarkdown('<script>alert(1)</script>安全内容')

    expect(html).not.toContain('<script')
    expect(html).toContain('安全内容')
  })
})
