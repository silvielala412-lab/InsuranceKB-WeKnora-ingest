import { describe, expect, it } from 'vitest'

import { parseV5DynamicFieldGapfillResponse } from './v5DynamicGapfillContract.ts'

const H = (character: string) => character.repeat(64)

describe('v5 dynamic field gapfill contract', () => {
  it('accepts a non-serving field diff with scope receipts', () => {
    const response = parseV5DynamicFieldGapfillResponse({
      contract: 'insurance-v5-dynamic-field-gapfill-response.v1',
      operation_id: 'gapfill-1',
      action: 'gapfill',
      status: 'IMPROVED',
      product_version_id: '596-1',
      base_preview_sha256: H('a'),
      serving_effect: 'NONE',
      review_publish_admission: false,
      call_count: 2,
      stages: [{
        scope: 'matched_snippets',
        scanned_page_count: 30,
        selected_page_count: 2,
        context_sha256: H('b'),
        outcome: 'NO_IMPROVEMENT',
      }, {
        scope: 'adjacent_pages',
        scanned_page_count: 30,
        selected_page_count: 4,
        context_sha256: H('c'),
        outcome: 'IMPROVED',
      }],
      fields: [{
        field_id: 'target_customer_profile',
        status: 'FILLED',
        scope_used: 'adjacent_pages',
        changed: true,
        before: { state: 'unknown', value: null, evidence: [] },
        proposed: {
          state: 'present',
          value: '家庭成员',
          evidence: [{
            source_revision_id: 'source-1',
            locator: 'pdf:条款.pdf#page=2',
            quote: '适用人群包括家庭成员',
            verification_status: 'VERIFIED',
            verification_error: null,
          }],
        },
        after: {
          state: 'present',
          value: '家庭成员',
          evidence: [{
            source_revision_id: 'source-1',
            locator: 'pdf:条款.pdf#page=2',
            quote: '适用人群包括家庭成员',
            verification_status: 'VERIFIED',
            verification_error: null,
          }],
        },
      }],
      candidate_preview: {
        contract: 'insurance-v5-candidate-preview.v2',
        catalog_id: 'insurance-product-schema-v5',
        catalog_sha256: H('d'),
        schema_id: 'insurance-product-schema-v5:医疗险',
        source_revision_id: 'source-1',
        insurance_class: '医疗险',
        product_id: '596',
        product_version_id: '596-1',
        product_display_name: '测试产品',
        serving_effect: 'NONE',
        review_publish_admission: false,
        categories: [{ ordinal: 0, category_id: '03', display_name: '产品定位与摘要' }],
        fields: [{
          ordinal: 0,
          category_id: '03',
          category_display_name: '产品定位与摘要',
          field_id: 'target_customer_profile',
          display_name: '适用人群',
          knowledge_role: '内容 Content',
          formation_modes: ['原文抽取', 'LLM生成'],
          output_kind: 'Content',
          state: 'present',
          value: '家庭成员',
          evidence: [{
            source_revision_id: 'source-1',
            locator: 'pdf:条款.pdf#page=2',
            quote: '适用人群包括家庭成员',
            verification_status: 'VERIFIED',
            verification_error: null,
          }],
        }],
        preview_sha256: H('e'),
      },
    })

    expect(response.fields[0]?.status).toBe('FILLED')
    expect(response.stages.map(stage => stage.scope)).toEqual([
      'matched_snippets',
      'adjacent_pages',
    ])
    expect(response.serving_effect).toBe('NONE')
  })

  it('rejects a response that claims a serving effect', () => {
    expect(() => parseV5DynamicFieldGapfillResponse({
      contract: 'insurance-v5-dynamic-field-gapfill-response.v1',
      serving_effect: 'ACTIVE',
    })).toThrow('V5_DYNAMIC_GAPFILL_CONTRACT_INVALID')
  })
})
