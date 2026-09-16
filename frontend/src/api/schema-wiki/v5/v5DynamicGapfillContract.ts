import {
  parseV5CandidatePreview,
  type V5CandidateEvidence,
  type V5CandidatePreview,
  type V5PreviewField,
} from './v5PreviewContract.ts'

export type V5DynamicFieldAction = 'gapfill' | 'review'
export type V5DynamicFieldScope = 'matched_snippets' | 'adjacent_pages' | 'all_material'
export type V5DynamicOperationStatus = 'IMPROVED' | 'CONFIRMED' | 'NEEDS_REVIEW' | 'NO_CHANGE'

export interface V5DynamicFieldGapfillRequest {
  readonly contract: 'insurance-v5-dynamic-field-gapfill-request.v1'
  readonly product_version_id: string
  readonly preview_sha256: string
  readonly action: V5DynamicFieldAction
  readonly field_ids: readonly string[]
}

export interface V5DynamicFieldSnapshot {
  readonly state: V5PreviewField['state']
  readonly value: V5PreviewField['value']
  readonly evidence: readonly V5CandidateEvidence[]
}

export interface V5DynamicStageReceipt {
  readonly scope: V5DynamicFieldScope
  readonly scanned_page_count: number
  readonly selected_page_count: number
  readonly context_sha256: string
  readonly outcome: 'NO_CANDIDATE' | 'NO_IMPROVEMENT' | 'IMPROVED' | 'CONFIRMED' | 'CONFLICT'
}

export interface V5DynamicFieldDiff {
  readonly field_id: string
  readonly status: 'FILLED' | 'CONFIRMED' | 'CONFLICT' | 'STILL_UNKNOWN' | 'UNCHANGED'
  readonly scope_used: V5DynamicFieldScope | null
  readonly changed: boolean
  readonly before: V5DynamicFieldSnapshot
  readonly proposed: V5DynamicFieldSnapshot | null
  readonly after: V5DynamicFieldSnapshot
}

export interface V5DynamicFieldGapfillResponse {
  readonly contract: 'insurance-v5-dynamic-field-gapfill-response.v1'
  readonly operation_id: string
  readonly action: V5DynamicFieldAction
  readonly status: V5DynamicOperationStatus
  readonly product_version_id: string
  readonly base_preview_sha256: string
  readonly serving_effect: 'NONE'
  readonly review_publish_admission: false
  readonly call_count: number
  readonly stages: readonly V5DynamicStageReceipt[]
  readonly fields: readonly V5DynamicFieldDiff[]
  readonly candidate_preview: V5CandidatePreview
}

const RESPONSE_KEYS = [
  'action',
  'base_preview_sha256',
  'call_count',
  'candidate_preview',
  'contract',
  'fields',
  'operation_id',
  'product_version_id',
  'review_publish_admission',
  'serving_effect',
  'stages',
  'status',
] as const
const STAGE_KEYS = [
  'context_sha256',
  'outcome',
  'scanned_page_count',
  'scope',
  'selected_page_count',
] as const
const DIFF_KEYS = [
  'after',
  'before',
  'changed',
  'field_id',
  'proposed',
  'scope_used',
  'status',
] as const
const SNAPSHOT_KEYS = ['evidence', 'state', 'value'] as const
const EVIDENCE_KEYS = [
  'locator',
  'quote',
  'source_revision_id',
  'verification_error',
  'verification_status',
] as const
const SCOPES: readonly V5DynamicFieldScope[] = [
  'matched_snippets',
  'adjacent_pages',
  'all_material',
]

function invalid(): never {
  throw new Error('V5_DYNAMIC_GAPFILL_CONTRACT_INVALID')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).sort().join('\u0000') === [...keys].sort().join('\u0000')
}

function isSha256(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
}

function isCandidateValue(value: unknown): value is V5PreviewField['value'] {
  return value === null
    || typeof value === 'string'
    || typeof value === 'number'
    || typeof value === 'boolean'
    || (Array.isArray(value) && value.every(item => typeof item === 'string'))
}

function parseEvidence(value: unknown, sourceRevisionId: string): V5CandidateEvidence {
  if (!isRecord(value) || !hasExactKeys(value, EVIDENCE_KEYS)) invalid()
  if (
    value.source_revision_id !== sourceRevisionId
    || typeof value.locator !== 'string'
    || !value.locator
    || typeof value.quote !== 'string'
    || !value.quote
    || !['VERIFIED', 'NORMALIZED_MATCH', 'UNRESOLVED', 'AMBIGUOUS'].includes(
      value.verification_status as string,
    )
    || !(value.verification_error === null || (
      typeof value.verification_error === 'string' && value.verification_error.length > 0
    ))
    || (
      ['VERIFIED', 'NORMALIZED_MATCH'].includes(value.verification_status as string)
      && value.verification_error !== null
    )
    || (
      ['UNRESOLVED', 'AMBIGUOUS'].includes(value.verification_status as string)
      && typeof value.verification_error !== 'string'
    )
  ) invalid()
  return Object.freeze({
    source_revision_id: value.source_revision_id,
    locator: value.locator,
    quote: value.quote,
    verification_status: value.verification_status as V5CandidateEvidence['verification_status'],
    verification_error: value.verification_error,
  })
}

function parseSnapshot(value: unknown, sourceRevisionId: string): V5DynamicFieldSnapshot {
  if (!isRecord(value) || !hasExactKeys(value, SNAPSHOT_KEYS)) invalid()
  if (
    !['present', 'absent_explicitly', 'unknown'].includes(value.state as string)
    || !isCandidateValue(value.value)
    || !Array.isArray(value.evidence)
  ) invalid()
  const evidence = Object.freeze(value.evidence.map(item => parseEvidence(item, sourceRevisionId)))
  if (
    (value.state === 'present' && (value.value === null || evidence.length === 0))
    || (value.state === 'absent_explicitly' && (value.value !== null || evidence.length === 0))
    || (value.state === 'unknown' && (value.value !== null || evidence.length !== 0))
  ) invalid()
  return Object.freeze({
    state: value.state as V5PreviewField['state'],
    value: Array.isArray(value.value) ? Object.freeze([...value.value]) : value.value,
    evidence,
  })
}

function parseStage(value: unknown, ordinal: number): V5DynamicStageReceipt {
  if (!isRecord(value) || !hasExactKeys(value, STAGE_KEYS)) invalid()
  if (
    value.scope !== SCOPES[ordinal]
    || !Number.isInteger(value.scanned_page_count)
    || (value.scanned_page_count as number) < 1
    || !Number.isInteger(value.selected_page_count)
    || (value.selected_page_count as number) < 0
    || (value.selected_page_count as number) > (value.scanned_page_count as number)
    || !isSha256(value.context_sha256)
    || !['NO_CANDIDATE', 'NO_IMPROVEMENT', 'IMPROVED', 'CONFIRMED', 'CONFLICT'].includes(
      value.outcome as string,
    )
  ) invalid()
  return Object.freeze({
    scope: value.scope as V5DynamicFieldScope,
    scanned_page_count: value.scanned_page_count as number,
    selected_page_count: value.selected_page_count as number,
    context_sha256: value.context_sha256,
    outcome: value.outcome as V5DynamicStageReceipt['outcome'],
  })
}

function parseDiff(value: unknown, sourceRevisionId: string): V5DynamicFieldDiff {
  if (!isRecord(value) || !hasExactKeys(value, DIFF_KEYS)) invalid()
  if (
    typeof value.field_id !== 'string'
    || !/^[a-z][a-z0-9_]*$/.test(value.field_id)
    || !['FILLED', 'CONFIRMED', 'CONFLICT', 'STILL_UNKNOWN', 'UNCHANGED'].includes(
      value.status as string,
    )
    || !(value.scope_used === null || SCOPES.includes(value.scope_used as V5DynamicFieldScope))
    || typeof value.changed !== 'boolean'
    || !(value.proposed === null || isRecord(value.proposed))
  ) invalid()
  return Object.freeze({
    field_id: value.field_id,
    status: value.status as V5DynamicFieldDiff['status'],
    scope_used: value.scope_used as V5DynamicFieldScope | null,
    changed: value.changed,
    before: parseSnapshot(value.before, sourceRevisionId),
    proposed: value.proposed === null ? null : parseSnapshot(value.proposed, sourceRevisionId),
    after: parseSnapshot(value.after, sourceRevisionId),
  })
}

export function parseV5DynamicFieldGapfillResponse(
  value: unknown,
): V5DynamicFieldGapfillResponse {
  if (!isRecord(value) || !hasExactKeys(value, RESPONSE_KEYS)) invalid()
  if (
    value.contract !== 'insurance-v5-dynamic-field-gapfill-response.v1'
    || typeof value.operation_id !== 'string'
    || !value.operation_id
    || !['gapfill', 'review'].includes(value.action as string)
    || !['IMPROVED', 'CONFIRMED', 'NEEDS_REVIEW', 'NO_CHANGE'].includes(value.status as string)
    || typeof value.product_version_id !== 'string'
    || !value.product_version_id
    || !isSha256(value.base_preview_sha256)
    || value.serving_effect !== 'NONE'
    || value.review_publish_admission !== false
    || !Number.isInteger(value.call_count)
    || (value.call_count as number) < 0
    || (value.call_count as number) > 3
    || !Array.isArray(value.stages)
    || value.stages.length < 1
    || value.stages.length > 3
    || !Array.isArray(value.fields)
    || value.fields.length < 1
    || value.fields.length > 8
  ) invalid()
  const candidatePreview = parseV5CandidatePreview(value.candidate_preview)
  if (candidatePreview.product_version_id !== value.product_version_id) invalid()
  const stages = Object.freeze(value.stages.map(parseStage))
  if (value.call_count !== stages.filter(stage => stage.selected_page_count > 0).length) invalid()
  const fields = Object.freeze(value.fields.map(
    field => parseDiff(field, candidatePreview.source_revision_id),
  ))
  if (new Set(fields.map(field => field.field_id)).size !== fields.length) invalid()
  return Object.freeze({
    contract: 'insurance-v5-dynamic-field-gapfill-response.v1',
    operation_id: value.operation_id,
    action: value.action as V5DynamicFieldAction,
    status: value.status as V5DynamicOperationStatus,
    product_version_id: value.product_version_id,
    base_preview_sha256: value.base_preview_sha256,
    serving_effect: 'NONE',
    review_publish_admission: false,
    call_count: value.call_count as number,
    stages,
    fields,
    candidate_preview: candidatePreview,
  })
}
