import type { V5PreviewField } from '../../../../api/schema-wiki/v5/v5PreviewContract.ts'

export interface V5FieldTable {
  readonly caption: string
  readonly columns: readonly string[]
  readonly rows: readonly (readonly string[])[]
}

function lines(value: string): string[] {
  return value
    .replace(/\r/g, '')
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
}

function splitCells(line: string): string[] {
  return line.replace(/(\d)\s+(年交|周岁|岁|万)/g, '$1$2')
    .split(/\s+/).map(cell => cell.trim()).filter(Boolean)
}

function parseAgeTable(value: string): V5FieldTable | null {
  const rows = lines(value)
    .map(splitCells)
    .filter(cells => cells.length === 5 && /^(?:趸交|\d+年交)$/.test(cells[0] ?? ''))
    .filter(cells => cells.slice(1).every(cell => /^\d+-\d+岁$/.test(cell)))

  if (rows.length === 0) return null
  return {
    caption: '投保年龄条件（按交费年期、被保险人人数和性别）',
    columns: ['交费年期', '单被保险人·男', '单被保险人·女', '双被保险人·男', '双被保险人·女'],
    rows,
  }
}

function parseInvestigationTable(value: string): V5FieldTable | null {
  const rows = lines(value)
    .map(splitCells)
    .filter(cells => cells.length === 4 && /^(?:\d+-\d+周岁|\d+周岁及以上)$/.test(cells[0] ?? ''))

  if (rows.length === 0) return null
  return {
    caption: '累计风险保额触发标准',
    columns: ['年龄', '契调标准（人身险）', '有效财务证明（人身险）', '体检（寿险）'],
    rows,
  }
}

export function parseV5FieldTable(field: V5PreviewField): V5FieldTable | null {
  if (field.state !== 'present' || typeof field.value !== 'string') return null
  if (field.field_id === 'entry_age_range') return parseAgeTable(field.value)
  if (field.field_id === 'underwriting_investigation_requirements') {
    return parseInvestigationTable(field.value)
  }
  return null
}
