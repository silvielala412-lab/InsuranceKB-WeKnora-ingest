import {
  parseV5CandidatePreview,
  type V5CandidatePreview,
} from './v5PreviewContract.ts'

export type V5ProviderRunStatus = 'COMPLETED' | 'PARTIAL' | 'FAILED'
export type V5ProviderProductStatus = 'SUCCESS' | 'REVIEW_REQUIRED' | 'FAILED'
export type V5ProviderAttemptOutcome =
  | 'ACCEPTED'
  | 'PRESERVED'
  | 'REJECTED'
  | 'ERROR'
  | 'REPAIR_REJECTED'

export interface V5ProviderAttemptReceipt {
  readonly attempt: number
  readonly outcome: V5ProviderAttemptOutcome
  readonly response_id: string | null
  readonly response_model: string | null
  readonly finish_reason: string | null
  readonly prompt_tokens: number | null
  readonly completion_tokens: number | null
  readonly total_tokens: number | null
  readonly error_code: string | null
}

export type V5MaterialSupportStatus = 'supported' | 'ambiguous' | 'unsupported'

export interface V5MaterialSupportDecision {
  readonly field_id: string
  readonly status: V5MaterialSupportStatus
  readonly basis: string
  readonly candidate_locators: readonly string[]
}

export interface V5MaterialSupportMetrics {
  readonly extractable_field_count: number
  readonly material_supported_field_count: number
  readonly material_supported_present_count: number
  readonly rate: number
  readonly ambiguous_field_count: number
  readonly unsupported_field_count: number
}

export interface V5ProviderTrialProduct {
  readonly product_id: string
  readonly product_version_id: string
  readonly product_display_name: string
  readonly insurance_class: string
  readonly schema_id: string
  readonly source_revision_id: string
  readonly source_manifest_sha256: string
  readonly status: V5ProviderProductStatus
  readonly error_code: string | null
  readonly files: readonly {
    readonly file_name: string
    readonly sha256: string
    readonly page_count: number
  }[]
  readonly attempts: readonly V5ProviderAttemptReceipt[]
  readonly preview: V5CandidatePreview | null
  readonly material_support: readonly V5MaterialSupportDecision[]
  readonly material_support_metrics: V5MaterialSupportMetrics | null
}

export interface V5ProviderTrialRun {
  readonly contract: 'insurance-v5-provider-trial-run.v2'
  readonly run_id: string
  readonly run_sha256: string
  readonly catalog_id: 'insurance-product-schema-v5'
  readonly catalog_sha256: string
  readonly status: V5ProviderRunStatus
  readonly provider: {
    readonly family: 'qwen'
    readonly base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    readonly model: 'qwen-plus'
    readonly mode: 'streaming-non-thinking-json'
  }
  readonly call_count: number
  readonly started_at: string
  readonly finished_at: string
  readonly serving_effect: 'NONE'
  readonly review_publish_admission: false
  readonly products: readonly V5ProviderTrialProduct[]
}

const RUN_KEYS = [
  'call_count',
  'catalog_id',
  'catalog_sha256',
  'contract',
  'finished_at',
  'products',
  'provider',
  'review_publish_admission',
  'run_id',
  'run_sha256',
  'serving_effect',
  'started_at',
  'status',
] as const
const PROVIDER_KEYS = ['base_url', 'family', 'mode', 'model'] as const
const PRODUCT_KEYS = [
  'attempts',
  'error_code',
  'files',
  'insurance_class',
  'preview',
  'product_display_name',
  'product_id',
  'product_version_id',
  'schema_id',
  'source_manifest_sha256',
  'source_revision_id',
  'status',
] as const
const PRODUCT_KEYS_M142 = [
  ...PRODUCT_KEYS,
  'material_support',
  'material_support_metrics',
] as const
const FILE_KEYS = ['file_name', 'page_count', 'sha256'] as const
const ATTEMPT_KEYS = [
  'attempt',
  'completion_tokens',
  'error_code',
  'finish_reason',
  'outcome',
  'prompt_tokens',
  'response_id',
  'response_model',
  'total_tokens',
] as const
const MAX_PROVIDER_RUN_CALLS = 32

function invalid(): never {
  throw new Error('V5_PROVIDER_TRIAL_CONTRACT_INVALID')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).sort().join('\u0000') === [...keys].sort().join('\u0000')
}

function nonEmpty(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

function isSha256(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
}

function optionalString(value: unknown): value is string | null {
  return value === null || nonEmpty(value)
}

function optionalCount(value: unknown): value is number | null {
  return value === null || (Number.isInteger(value) && (value as number) >= 0)
}

function parseMaterialSupport(value: unknown): readonly V5MaterialSupportDecision[] {
  if (!Array.isArray(value)) invalid()
  return Object.freeze(value.map(item => {
    if (
      !isRecord(item)
      || !hasExactKeys(item, ['basis', 'candidate_locators', 'field_id', 'status'])
      || !nonEmpty(item.field_id)
      || !['supported', 'ambiguous', 'unsupported'].includes(item.status as string)
      || !nonEmpty(item.basis)
      || !Array.isArray(item.candidate_locators)
      || !item.candidate_locators.every(locator => nonEmpty(locator))
    ) invalid()
    return Object.freeze({
      field_id: item.field_id,
      status: item.status as V5MaterialSupportStatus,
      basis: item.basis,
      candidate_locators: Object.freeze(item.candidate_locators as string[]),
    })
  }))
}

function parseMaterialSupportMetrics(value: unknown): V5MaterialSupportMetrics {
  if (
    !isRecord(value)
    || !hasExactKeys(value, [
      'ambiguous_field_count',
      'extractable_field_count',
      'material_supported_field_count',
      'material_supported_present_count',
      'rate',
      'unsupported_field_count',
    ])
    || !Number.isInteger(value.extractable_field_count)
    || (value.extractable_field_count as number) < 0
    || !Number.isInteger(value.material_supported_field_count)
    || (value.material_supported_field_count as number) < 0
    || !Number.isInteger(value.material_supported_present_count)
    || (value.material_supported_present_count as number) < 0
    || typeof value.rate !== 'number'
    || !Number.isFinite(value.rate)
    || value.rate < 0
    || value.rate > 1
    || !Number.isInteger(value.ambiguous_field_count)
    || (value.ambiguous_field_count as number) < 0
    || !Number.isInteger(value.unsupported_field_count)
    || (value.unsupported_field_count as number) < 0
  ) invalid()
  return Object.freeze({
    extractable_field_count: value.extractable_field_count as number,
    material_supported_field_count: value.material_supported_field_count as number,
    material_supported_present_count: value.material_supported_present_count as number,
    rate: value.rate as number,
    ambiguous_field_count: value.ambiguous_field_count as number,
    unsupported_field_count: value.unsupported_field_count as number,
  })
}

function parseAttempt(value: unknown, expectedAttempt: number): V5ProviderAttemptReceipt {
  if (!isRecord(value) || !hasExactKeys(value, ATTEMPT_KEYS)) invalid()
  if (
    value.attempt !== expectedAttempt
    || !['ACCEPTED', 'PRESERVED', 'REJECTED', 'ERROR', 'REPAIR_REJECTED'].includes(value.outcome as string)
    || !optionalString(value.response_id)
    || !optionalString(value.response_model)
    || !optionalString(value.finish_reason)
    || !optionalCount(value.prompt_tokens)
    || !optionalCount(value.completion_tokens)
    || !optionalCount(value.total_tokens)
    || !optionalString(value.error_code)
    || (value.outcome === 'ACCEPTED' && value.error_code !== null)
    || (
      value.outcome === 'PRESERVED'
      && !['EVIDENCE_REVIEW_REQUIRED', 'EXTRACTION_GAP_REVIEW_REQUIRED'].includes(
        value.error_code as string,
      )
    )
    || (
      value.outcome === 'REPAIR_REJECTED'
      && (expectedAttempt < 2 || !nonEmpty(value.error_code))
    )
    || (['REJECTED', 'ERROR'].includes(value.outcome as string) && !nonEmpty(value.error_code))
  ) invalid()
  return Object.freeze({
    attempt: expectedAttempt,
    outcome: value.outcome as V5ProviderAttemptOutcome,
    response_id: value.response_id,
    response_model: value.response_model,
    finish_reason: value.finish_reason,
    prompt_tokens: value.prompt_tokens,
    completion_tokens: value.completion_tokens,
    total_tokens: value.total_tokens,
    error_code: value.error_code,
  })
}

function parseProduct(value: unknown): V5ProviderTrialProduct {
  if (!isRecord(value)) invalid()
  const isLegacyProduct = hasExactKeys(value, PRODUCT_KEYS)
  const isM142Product = hasExactKeys(value, PRODUCT_KEYS_M142)
  if (!isLegacyProduct && !isM142Product) invalid()
  if (
    !nonEmpty(value.product_id)
    || !nonEmpty(value.product_version_id)
    || !nonEmpty(value.product_display_name)
    || !nonEmpty(value.insurance_class)
    || value.schema_id !== `insurance-product-schema-v5:${value.insurance_class}`
    || !nonEmpty(value.source_revision_id)
    || !isSha256(value.source_manifest_sha256)
    || !['SUCCESS', 'REVIEW_REQUIRED', 'FAILED'].includes(value.status as string)
    || !optionalString(value.error_code)
    || !Array.isArray(value.files)
    || value.files.length < 1
    || !Array.isArray(value.attempts)
    || value.attempts.length < 1
    || value.attempts.length > MAX_PROVIDER_RUN_CALLS
  ) invalid()
  const files = Object.freeze(value.files.map(file => {
    if (
      !isRecord(file)
      || !hasExactKeys(file, FILE_KEYS)
      || !nonEmpty(file.file_name)
      || !isSha256(file.sha256)
      || !Number.isInteger(file.page_count)
      || (file.page_count as number) < 1
    ) invalid()
    return Object.freeze({
      file_name: file.file_name,
      sha256: file.sha256,
      page_count: file.page_count as number,
    })
  }))
  const attempts = Object.freeze(value.attempts.map((attempt, index) => (
    parseAttempt(attempt, index + 1)
  )))
  const preview = value.preview === null ? null : parseV5CandidatePreview(value.preview)
  const material_support = isM142Product
    ? parseMaterialSupport(value.material_support)
    : Object.freeze([])
  const material_support_metrics = isM142Product
    ? value.material_support_metrics === null
      ? null
      : parseMaterialSupportMetrics(value.material_support_metrics)
    : null
  if (
    (value.status === 'SUCCESS' && (
      value.error_code !== null
      || preview === null
      || attempts.at(-1)?.outcome !== 'ACCEPTED'
      || preview.product_id !== value.product_id
      || preview.product_version_id !== value.product_version_id
      || preview.product_display_name !== value.product_display_name
      || preview.insurance_class !== value.insurance_class
      || preview.schema_id !== value.schema_id
      || preview.source_revision_id !== value.source_revision_id
    ))
    || (value.status === 'REVIEW_REQUIRED' && (
      !['EVIDENCE_REVIEW_REQUIRED', 'EXTRACTION_GAP_REVIEW_REQUIRED'].includes(
        value.error_code as string,
      )
      || preview === null
      || !['PRESERVED', 'REPAIR_REJECTED'].includes(attempts.at(-1)?.outcome ?? '')
      || preview.product_id !== value.product_id
      || preview.product_version_id !== value.product_version_id
      || preview.product_display_name !== value.product_display_name
      || preview.insurance_class !== value.insurance_class
      || preview.schema_id !== value.schema_id
      || preview.source_revision_id !== value.source_revision_id
    ))
    || (value.status === 'FAILED' && (!nonEmpty(value.error_code) || preview !== null))
  ) invalid()
  return Object.freeze({
    product_id: value.product_id,
    product_version_id: value.product_version_id,
    product_display_name: value.product_display_name,
    insurance_class: value.insurance_class,
    schema_id: value.schema_id,
    source_revision_id: value.source_revision_id,
    source_manifest_sha256: value.source_manifest_sha256,
    status: value.status as V5ProviderProductStatus,
    error_code: value.error_code,
    files,
    attempts,
    preview,
    material_support,
    material_support_metrics,
  })
}

export function parseV5ProviderTrialRun(value: unknown): V5ProviderTrialRun {
  if (!isRecord(value) || !hasExactKeys(value, RUN_KEYS)) invalid()
  if (
    value.contract !== 'insurance-v5-provider-trial-run.v2'
    || !nonEmpty(value.run_id)
    || !isSha256(value.run_sha256)
    || value.catalog_id !== 'insurance-product-schema-v5'
    || !isSha256(value.catalog_sha256)
    || !['COMPLETED', 'PARTIAL', 'FAILED'].includes(value.status as string)
    || !isRecord(value.provider)
    || !hasExactKeys(value.provider, PROVIDER_KEYS)
    || value.provider.family !== 'qwen'
    || value.provider.base_url !== 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    || value.provider.model !== 'qwen-plus'
    || value.provider.mode !== 'streaming-non-thinking-json'
    || !Number.isInteger(value.call_count)
    || (value.call_count as number) < 1
    || (value.call_count as number) > MAX_PROVIDER_RUN_CALLS
    || !nonEmpty(value.started_at)
    || !nonEmpty(value.finished_at)
    || value.serving_effect !== 'NONE'
    || value.review_publish_admission !== false
    || !Array.isArray(value.products)
    || value.products.length < 1
    || value.products.length > 9
  ) invalid()
  const products = Object.freeze(value.products.map(parseProduct))
  const previewCount = products.filter(product => product.preview !== null).length
  const expectedStatus = previewCount === products.length
    ? 'COMPLETED'
    : previewCount > 0 ? 'PARTIAL' : 'FAILED'
  if (
    products.reduce((count, product) => count + product.attempts.length, 0) !== value.call_count
    || expectedStatus !== value.status
    || new Set(products.map(product => product.product_version_id)).size !== products.length
  ) invalid()
  return Object.freeze({
    contract: 'insurance-v5-provider-trial-run.v2',
    run_id: value.run_id,
    run_sha256: value.run_sha256,
    catalog_id: 'insurance-product-schema-v5',
    catalog_sha256: value.catalog_sha256,
    status: value.status as V5ProviderRunStatus,
    provider: Object.freeze({
      family: 'qwen',
      base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      model: 'qwen-plus',
      mode: 'streaming-non-thinking-json',
    }),
    call_count: value.call_count as number,
    started_at: value.started_at,
    finished_at: value.finished_at,
    serving_effect: 'NONE',
    review_publish_admission: false,
    products,
  })
}
