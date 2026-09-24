import { describe, expect, it } from 'vitest'

import { buildV5ConceptIndex } from './v5Concepts.ts'
import type { V5CandidatePreview } from '../../../../api/schema-wiki/v5/v5PreviewContract.ts'

const H = (character: string) => character.repeat(64)

function preview(
  productId: string,
  productName: string,
  value: string | null,
  state: 'present' | 'unknown' = value === null ? 'unknown' : 'present',
): V5CandidatePreview {
  return {
    contract: 'insurance-v5-candidate-preview.v2',
    catalog_id: 'insurance-product-schema-v5',
    catalog_sha256: H('a'),
    schema_id: 'insurance-product-schema-v5:医疗险',
    source_revision_id: `source-${productId}`,
    insurance_class: '医疗险',
    product_id: productId,
    product_version_id: `${productId}@v1`,
    product_display_name: productName,
    serving_effect: 'NONE',
    review_publish_admission: false,
    categories: [{ ordinal: 0, category_id: '02', display_name: '产品主数据' }],
    fields: [{
      ordinal: 0,
      category_id: '02',
      category_display_name: '产品主数据',
      field_id: 'product_short_name',
      display_name: '产品简称',
      knowledge_role: '事实 Fact',
      formation_modes: ['原文抽取'],
      output_kind: 'Fact',
      state,
      value,
      evidence: state === 'present' ? [{
        source_revision_id: `source-${productId}`,
        verification_status: 'VERIFIED',
        verification_error: null,
        locator: 'page:1',
        quote: `产品简称：${value}`,
      }] : [],
    }],
    preview_sha256: H(productId[0]),
  }
}

describe('buildV5ConceptIndex', () => {
  it('relates present product fields while omitting unknown entities', () => {
    const concepts = buildV5ConceptIndex([
      preview('596', 'e生保尊享', 'e生保尊享'),
      preview('5003', '创金尊分红26', '创金尊分红26'),
      preview('594', 'e生保惠享', null),
    ])

    expect(concepts).toHaveLength(1)
    expect(concepts[0]).toMatchObject({
      concept_id: 'product_short_name',
      title: '产品简称',
      related_product_count: 2,
    })
    expect(concepts[0].instances.map(instance => instance.product_id)).toEqual(['596', '5003'])
  })
})
