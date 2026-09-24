import type { V5PreviewField } from './v5PreviewContract.ts'

export type V5SearchProvider = 'local' | 'bailian'

export interface V5SearchEvidence {
  readonly locator: string
  readonly quote: string
  readonly verification_status: 'VERIFIED' | 'NORMALIZED_MATCH' | 'UNRESOLVED' | 'AMBIGUOUS'
}

export interface V5SearchMatch {
  readonly product_id: string
  readonly product_version_id: string
  readonly product_display_name: string
  readonly insurance_class: string
  readonly field_id: string
  readonly field_display_name: string
  readonly category_display_name: string
  readonly value: V5PreviewField['value']
  readonly score: number
  readonly evidence: readonly V5SearchEvidence[]
}

export interface V5SearchResult {
  readonly contract: 'insurance-v5-search-response.v1'
  readonly query: string
  readonly provider: V5SearchProvider
  readonly model: string | null
  readonly answer: string
  readonly matches: readonly V5SearchMatch[]
  readonly provider_error: string | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isValue(value: unknown): value is V5PreviewField['value'] {
  return value === null
    || typeof value === 'string'
    || typeof value === 'number'
    || typeof value === 'boolean'
    || (Array.isArray(value) && value.every(item => typeof item === 'string'))
}

function invalid(): never {
  throw new Error('V5_SEARCH_RESPONSE_INVALID')
}

export function parseV5SearchResult(value: unknown): V5SearchResult {
  if (
    !isRecord(value)
    || value.contract !== 'insurance-v5-search-response.v1'
    || typeof value.query !== 'string'
    || !value.query
    || !['local', 'bailian'].includes(value.provider as string)
    || !(value.model === null || typeof value.model === 'string')
    || typeof value.answer !== 'string'
    || !value.answer
    || !Array.isArray(value.matches)
    || !(value.provider_error === null || typeof value.provider_error === 'string')
  ) invalid()
  const matches = value.matches.map(item => {
    if (
      !isRecord(item)
      || typeof item.product_id !== 'string'
      || typeof item.product_version_id !== 'string'
      || typeof item.product_display_name !== 'string'
      || typeof item.insurance_class !== 'string'
      || typeof item.field_id !== 'string'
      || typeof item.field_display_name !== 'string'
      || typeof item.category_display_name !== 'string'
      || !isValue(item.value)
      || typeof item.score !== 'number'
      || !Number.isInteger(item.score)
      || item.score < 1
      || !Array.isArray(item.evidence)
    ) invalid()
    const evidence = item.evidence.map(entry => {
      if (
        !isRecord(entry)
        || typeof entry.locator !== 'string'
        || !entry.locator
        || typeof entry.quote !== 'string'
        || !entry.quote
        || !['VERIFIED', 'NORMALIZED_MATCH', 'UNRESOLVED', 'AMBIGUOUS'].includes(
          entry.verification_status as string,
        )
      ) invalid()
      return Object.freeze({
        locator: entry.locator,
        quote: entry.quote,
        verification_status: entry.verification_status as V5SearchEvidence['verification_status'],
      })
    })
    return Object.freeze({
      product_id: item.product_id,
      product_version_id: item.product_version_id,
      product_display_name: item.product_display_name,
      insurance_class: item.insurance_class,
      field_id: item.field_id,
      field_display_name: item.field_display_name,
      category_display_name: item.category_display_name,
      value: item.value,
      score: item.score,
      evidence: Object.freeze(evidence),
    })
  })
  return Object.freeze({
    contract: 'insurance-v5-search-response.v1',
    query: value.query,
    provider: value.provider as V5SearchProvider,
    model: value.model,
    answer: value.answer,
    matches: Object.freeze(matches),
    provider_error: value.provider_error,
  })
}
