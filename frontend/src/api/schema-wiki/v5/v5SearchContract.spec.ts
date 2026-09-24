import { describe, expect, it } from 'vitest'

import { parseV5SearchResult } from './v5SearchContract.ts'

describe('parseV5SearchResult', () => {
  it('parses local matches and keeps evidence attached to the field', () => {
    const result = parseV5SearchResult({
      contract: 'insurance-v5-search-response.v1',
      query: '产品简称',
      provider: 'local',
      model: null,
      answer: '检索到 1 条相关字段。',
      provider_error: null,
      matches: [{
        product_id: '596',
        product_version_id: '596@v1',
        product_display_name: '平安e生保（尊享版）医疗保险',
        insurance_class: '医疗险',
        field_id: 'product_short_name',
        field_display_name: '产品简称',
        category_display_name: '产品主数据',
        value: 'e生保尊享',
        score: 8,
        evidence: [{
          locator: 'pdf:rules.pdf#page=1',
          quote: '产品简称：e生保尊享',
          verification_status: 'VERIFIED',
        }],
      }],
    })

    expect(result.provider).toBe('local')
    expect(result.matches[0]?.value).toBe('e生保尊享')
    expect(result.matches[0]?.evidence[0]?.quote).toContain('e生保尊享')
  })
})
