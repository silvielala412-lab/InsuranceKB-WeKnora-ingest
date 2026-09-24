import type {
  V5CandidatePreview,
  V5PreviewField,
} from '../../../../api/schema-wiki/v5/v5PreviewContract.ts'

export interface V5ConceptInstance {
  readonly product_id: string
  readonly product_version_id: string
  readonly product_display_name: string
  readonly insurance_class: string
  readonly field_id: string
  readonly field_display_name: string
  readonly category_display_name: string
  readonly state: V5PreviewField['state']
  readonly value: V5PreviewField['value']
  readonly evidence_count: number
}

export interface V5Concept {
  readonly concept_id: string
  readonly title: string
  readonly category_display_name: string
  readonly instances: readonly V5ConceptInstance[]
  readonly related_product_count: number
}

function hasValue(value: V5PreviewField['value']): boolean {
  if (Array.isArray(value)) return value.length > 0
  return value !== null && String(value).trim().length > 0
}

/**
 * Builds a navigational concept index from the already loaded product previews.
 * Values remain attached to their product entity; the concept only relates them.
 */
export function buildV5ConceptIndex(
  previews: readonly V5CandidatePreview[],
): readonly V5Concept[] {
  const groups = new Map<string, {
    title: string
    category_display_name: string
    first_ordinal: number
    instances: V5ConceptInstance[]
  }>()

  for (const preview of previews) {
    for (const field of preview.fields) {
      if (field.state !== 'present' || !hasValue(field.value)) continue
      const current = groups.get(field.field_id) ?? {
        title: field.display_name,
        category_display_name: field.category_display_name,
        first_ordinal: field.ordinal,
        instances: [],
      }
      current.first_ordinal = Math.min(current.first_ordinal, field.ordinal)
      current.instances.push({
        product_id: preview.product_id,
        product_version_id: preview.product_version_id,
        product_display_name: preview.product_display_name,
        insurance_class: preview.insurance_class,
        field_id: field.field_id,
        field_display_name: field.display_name,
        category_display_name: field.category_display_name,
        state: field.state,
        value: field.value,
        evidence_count: field.evidence.length,
      })
      groups.set(field.field_id, current)
    }
  }

  return Object.freeze(
    [...groups.entries()]
      .map(([concept_id, group]) => ({
        concept_id,
        title: group.title,
        category_display_name: group.category_display_name,
        instances: Object.freeze(group.instances),
        related_product_count: new Set(group.instances.map(instance => instance.product_id)).size,
        first_ordinal: group.first_ordinal,
      }))
      .sort((left, right) => (
        left.first_ordinal - right.first_ordinal
        || left.title.localeCompare(right.title)
      ))
      .map(entry => {
        const { first_ordinal: _firstOrdinal, ...concept } = entry
        return Object.freeze(concept)
      }),
  )
}
