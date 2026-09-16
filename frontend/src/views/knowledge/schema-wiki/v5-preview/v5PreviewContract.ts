export type V5TriState = 'present' | 'absent_explicitly' | 'unknown'
export type V5OutputKind = 'Fact' | 'Relation' | 'Derived' | 'Content'
export type V5EvidenceVerificationStatus =
  | 'VERIFIED'
  | 'NORMALIZED_MATCH'
  | 'UNRESOLVED'
  | 'AMBIGUOUS'
export type V5FormationMode = '外部映射' | '规则衍生' | 'LLM生成' | '原文抽取'

export interface V5CandidateEvidence {
  readonly source_revision_id: string
  readonly locator: string
  readonly quote: string
  readonly verification_status: V5EvidenceVerificationStatus
  readonly verification_error: string | null
}

export interface V5PreviewCategory {
  readonly ordinal: number
  readonly category_id: string
  readonly display_name: string
}

export interface V5PreviewField {
  readonly ordinal: number
  readonly category_id: string
  readonly category_display_name: string
  readonly field_id: string
  readonly display_name: string
  readonly knowledge_role: string
  readonly formation_modes: readonly V5FormationMode[]
  readonly output_kind: V5OutputKind
  readonly state: V5TriState
  readonly value: string | number | boolean | readonly string[] | null
  readonly evidence: readonly V5CandidateEvidence[]
}

export interface V5CandidatePreview {
  readonly contract: 'insurance-v5-candidate-preview.v2'
  readonly catalog_id: 'insurance-product-schema-v5'
  readonly catalog_sha256: string
  readonly schema_id: string
  readonly source_revision_id: string
  readonly insurance_class: string
  readonly product_id: string
  readonly product_version_id: string
  readonly product_display_name: string
  readonly serving_effect: 'NONE'
  readonly review_publish_admission: false
  readonly categories: readonly V5PreviewCategory[]
  readonly fields: readonly V5PreviewField[]
  readonly preview_sha256: string
}

const PREVIEW_KEYS = [
  'catalog_id',
  'catalog_sha256',
  'categories',
  'contract',
  'fields',
  'insurance_class',
  'preview_sha256',
  'product_display_name',
  'product_id',
  'product_version_id',
  'review_publish_admission',
  'schema_id',
  'serving_effect',
  'source_revision_id',
] as const
const CATEGORY_KEYS = ['category_id', 'display_name', 'ordinal'] as const
const FIELD_KEYS = [
  'category_display_name',
  'category_id',
  'display_name',
  'evidence',
  'field_id',
  'formation_modes',
  'knowledge_role',
  'ordinal',
  'output_kind',
  'state',
  'value',
] as const
const EVIDENCE_KEYS = [
  'locator',
  'quote',
  'source_revision_id',
  'verification_error',
  'verification_status',
] as const
const OUTPUT_KINDS = new Set<V5OutputKind>(['Fact', 'Relation', 'Derived', 'Content'])
const FORMATION_MODES = new Set<V5FormationMode>(['外部映射', '规则衍生', 'LLM生成', '原文抽取'])
const ROLE_TO_KIND = new Map<string, V5OutputKind>([
  ['事实 Fact', 'Fact'],
  ['关系 Relation', 'Relation'],
  ['衍生 Derived', 'Derived'],
  ['内容 Content', 'Content'],
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).sort().join('\u0000') === [...keys].sort().join('\u0000')
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

function isSha256(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
}

function invalid(): never {
  throw new Error('V5_PREVIEW_CONTRACT_INVALID')
}

function parseEvidence(value: unknown, sourceRevisionId: string): V5CandidateEvidence {
  if (!isRecord(value) || !hasExactKeys(value, EVIDENCE_KEYS)) invalid()
  if (
    value.source_revision_id !== sourceRevisionId
    || !nonEmptyString(value.locator)
    || !nonEmptyString(value.quote)
    || !['VERIFIED', 'NORMALIZED_MATCH', 'UNRESOLVED', 'AMBIGUOUS'].includes(
      value.verification_status as string,
    )
    || !(value.verification_error === null || nonEmptyString(value.verification_error))
    || (
      ['VERIFIED', 'NORMALIZED_MATCH'].includes(value.verification_status as string)
      && value.verification_error !== null
    )
    || (
      ['UNRESOLVED', 'AMBIGUOUS'].includes(value.verification_status as string)
      && !nonEmptyString(value.verification_error)
    )
  ) invalid()
  return Object.freeze({
    source_revision_id: value.source_revision_id,
    locator: value.locator,
    quote: value.quote,
    verification_status: value.verification_status as V5EvidenceVerificationStatus,
    verification_error: value.verification_error,
  })
}

function parseCategory(value: unknown): V5PreviewCategory {
  if (!isRecord(value) || !hasExactKeys(value, CATEGORY_KEYS)) invalid()
  if (
    !Number.isInteger(value.ordinal)
    || (value.ordinal as number) < 0
    || typeof value.category_id !== 'string'
    || !/^\d{2}$/.test(value.category_id)
    || !nonEmptyString(value.display_name)
  ) invalid()
  return Object.freeze({
    ordinal: value.ordinal as number,
    category_id: value.category_id,
    display_name: value.display_name,
  })
}

function isCandidateValue(value: unknown): value is V5PreviewField['value'] {
  return value === null
    || typeof value === 'string'
    || typeof value === 'number'
    || typeof value === 'boolean'
    || (Array.isArray(value) && value.every(item => typeof item === 'string'))
}

function parseField(
  value: unknown,
  ordinal: number,
  sourceRevisionId: string,
  categories: ReadonlyMap<string, string>,
): V5PreviewField {
  if (!isRecord(value) || !hasExactKeys(value, FIELD_KEYS)) invalid()
  if (
    value.ordinal !== ordinal
    || !nonEmptyString(value.category_id)
    || categories.get(value.category_id) !== value.category_display_name
    || !nonEmptyString(value.field_id)
    || !/^[a-z][a-z0-9_]*$/.test(value.field_id)
    || !nonEmptyString(value.display_name)
    || !nonEmptyString(value.knowledge_role)
    || !OUTPUT_KINDS.has(value.output_kind as V5OutputKind)
    || ROLE_TO_KIND.get(value.knowledge_role) !== value.output_kind
    || !Array.isArray(value.formation_modes)
    || value.formation_modes.length === 0
    || !value.formation_modes.every(mode => FORMATION_MODES.has(mode as V5FormationMode))
    || !['present', 'absent_explicitly', 'unknown'].includes(value.state as string)
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
    ordinal,
    category_id: value.category_id,
    category_display_name: value.category_display_name as string,
    field_id: value.field_id,
    display_name: value.display_name,
    knowledge_role: value.knowledge_role,
    formation_modes: Object.freeze([...(value.formation_modes as V5FormationMode[])]),
    output_kind: value.output_kind as V5OutputKind,
    state: value.state as V5TriState,
    value: Array.isArray(value.value) ? Object.freeze([...value.value]) : value.value,
    evidence,
  })
}

export function parseV5CandidatePreview(value: unknown): V5CandidatePreview {
  if (!isRecord(value) || !hasExactKeys(value, PREVIEW_KEYS)) invalid()
  if (
    value.contract !== 'insurance-v5-candidate-preview.v2'
    || value.catalog_id !== 'insurance-product-schema-v5'
    || !isSha256(value.catalog_sha256)
    || !nonEmptyString(value.schema_id)
    || !nonEmptyString(value.source_revision_id)
    || !nonEmptyString(value.insurance_class)
    || !nonEmptyString(value.product_id)
    || !nonEmptyString(value.product_version_id)
    || !nonEmptyString(value.product_display_name)
    || value.serving_effect !== 'NONE'
    || value.review_publish_admission !== false
    || !Array.isArray(value.categories)
    || !Array.isArray(value.fields)
    || !isSha256(value.preview_sha256)
  ) invalid()

  const categories = Object.freeze(value.categories.map(parseCategory))
  if (categories.some((category, index) => (
    index > 0 && category.ordinal <= categories[index - 1]!.ordinal
  ))) invalid()
  const categoryMap = new Map(categories.map(category => [category.category_id, category.display_name]))
  if (categoryMap.size !== categories.length) invalid()
  const fields = Object.freeze(value.fields.map((field, ordinal) => parseField(
    field,
    ordinal,
    value.source_revision_id as string,
    categoryMap,
  )))
  if (new Set(fields.map(field => field.field_id)).size !== fields.length) invalid()
  const firstCategoryOrder = [...new Set(fields.map(field => field.category_id))]
  if (firstCategoryOrder.join('\u0000') !== categories.map(category => category.category_id).join('\u0000')) {
    invalid()
  }

  return Object.freeze({
    contract: 'insurance-v5-candidate-preview.v2',
    catalog_id: 'insurance-product-schema-v5',
    catalog_sha256: value.catalog_sha256 as string,
    schema_id: value.schema_id as string,
    source_revision_id: value.source_revision_id as string,
    insurance_class: value.insurance_class as string,
    product_id: value.product_id as string,
    product_version_id: value.product_version_id as string,
    product_display_name: value.product_display_name as string,
    serving_effect: 'NONE',
    review_publish_admission: false,
    categories,
    fields,
    preview_sha256: value.preview_sha256 as string,
  })
}

export interface V5PreviewNavigationClass {
  readonly insurance_class: string
  readonly products: readonly {
    readonly product_id: string
    readonly product_version_id: string
    readonly product_display_name: string
    readonly preview: V5CandidatePreview
    readonly categories: readonly (V5PreviewCategory & {
      readonly fields: readonly V5PreviewField[]
    })[]
  }[]
}

export function projectV5PreviewNavigation(
  previews: readonly V5CandidatePreview[],
): readonly V5PreviewNavigationClass[] {
  const byClass = new Map<string, V5CandidatePreview[]>()
  for (const preview of previews) {
    const products = byClass.get(preview.insurance_class) ?? []
    if (products.some(item => item.product_version_id === preview.product_version_id)) invalid()
    products.push(preview)
    byClass.set(preview.insurance_class, products)
  }

  return Object.freeze([...byClass].map(([insuranceClass, products]) => Object.freeze({
    insurance_class: insuranceClass,
    products: Object.freeze(products.map(preview => Object.freeze({
      product_id: preview.product_id,
      product_version_id: preview.product_version_id,
      product_display_name: preview.product_display_name,
      preview,
      categories: Object.freeze(preview.categories.map(category => Object.freeze({
        ...category,
        fields: Object.freeze(preview.fields.filter(field => field.category_id === category.category_id)),
      }))),
    }))),
  })))
}
