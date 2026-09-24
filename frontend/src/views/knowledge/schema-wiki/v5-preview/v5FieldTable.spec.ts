import { describe, expect, it } from 'vitest'

import { parseV5FieldTable } from './v5FieldTable.ts'

const evidence = [{
  source_revision_id: 'source-a',
  locator: 'page:1',
  quote: 'table',
  verification_status: 'VERIFIED' as const,
  verification_error: null,
}]

function field(field_id: string, value: string) {
  return {
    ordinal: 0,
    category_id: '04',
    category_display_name: '投保与承保规则',
    field_id,
    display_name: '字段',
    knowledge_role: '事实 Fact',
    formation_modes: ['原文抽取' as const],
    output_kind: 'Fact' as const,
    state: 'present' as const,
    value,
    evidence,
  }
}

describe('V5 field table projection', () => {
  it('keeps source PDF spaces inside units from splitting table cells', () => {
    expect(parseV5FieldTable(field('entry_age_range',
      '20 年交 0-59 岁 0-60 岁 0-55 岁 0-55 岁'))?.rows).toEqual([
      ['20年交', '0-59岁', '0-60岁', '0-55岁', '0-55岁'],
    ])
    expect(parseV5FieldTable(field('underwriting_investigation_requirements',
      '71 周岁及以上 通用规则 通用规则 >100 万'))?.rows).toEqual([
      ['71周岁及以上', '通用规则', '通用规则', '>100万'],
    ])
  })

  it('projects the 6-row age grid into explicit grouped columns', () => {
    const table = parseV5FieldTable(field('entry_age_range', [
      '单被保险人 双被保险人',
      '交费年期',
      '男 女 男 女',
      '趸交 0-67岁 0-71岁 0-67岁 0-70岁',
      '3年交 0-66岁 0-69岁 0-66岁 0-69岁',
      '6年交 0-65岁 0-68岁 0-65岁 0-68岁',
      '10年交 0-63岁 0-66岁 0-63岁 0-65岁',
      '15年交 0-60岁 0-64岁 0-60岁 0-60岁',
      '20年交 0-59岁 0-60岁 0-55岁 0-55岁',
    ].join('\n')))
    expect(table?.columns).toEqual([
      '交费年期',
      '单被保险人·男',
      '单被保险人·女',
      '双被保险人·男',
      '双被保险人·女',
    ])
    expect(table?.rows).toHaveLength(6)
    expect(table?.rows[5]).toEqual(['20年交', '0-59岁', '0-60岁', '0-55岁', '0-55岁'])
  })

  it('projects the investigation thresholds and leaves unrelated text alone', () => {
    const table = parseV5FieldTable(field('underwriting_investigation_requirements', [
      '年龄 契调标准（人身险） 有效财务证明（人身险） 体检（寿险）',
      '18-45周岁 >1500万 >1500万 >1500万',
      '46-55周岁 >1200万 >1200万 >1200万',
      '56-65周岁 >800万 >800万 >800万',
      '66-70周岁 通用规则 通用规则 >200万',
      '71周岁及以上 通用规则 通用规则 >100万',
    ].join('\n')))
    expect(table?.rows).toEqual([
      ['18-45周岁', '>1500万', '>1500万', '>1500万'],
      ['46-55周岁', '>1200万', '>1200万', '>1200万'],
      ['56-65周岁', '>800万', '>800万', '>800万'],
      ['66-70周岁', '通用规则', '通用规则', '>200万'],
      ['71周岁及以上', '通用规则', '通用规则', '>100万'],
    ])
    expect(parseV5FieldTable(field('purchase_limitations', '最低保费：\n趸交：100万元；'))).toBeNull()
  })
})
