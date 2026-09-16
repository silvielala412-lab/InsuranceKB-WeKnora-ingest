import assert from 'node:assert/strict'
import test from 'node:test'

import {
  parseV5CandidatePreview,
  projectV5PreviewNavigation,
} from '../../../../api/schema-wiki/v5/v5PreviewContract.ts'

const H = (character: string) => character.repeat(64)

function preview(input: {
  insuranceClass: string
  productId: string
  categoryId: string
  fieldId: string
}) {
  return {
    contract: 'insurance-v5-candidate-preview.v2',
    catalog_id: 'insurance-product-schema-v5',
    catalog_sha256: H('a'),
    schema_id: `insurance-product-schema-v5:${input.insuranceClass}`,
    source_revision_id: `source-${input.productId}`,
    insurance_class: input.insuranceClass,
    product_id: input.productId,
    product_version_id: `${input.productId}@v1`,
    product_display_name: `${input.productId}名称`,
    serving_effect: 'NONE',
    review_publish_admission: false,
    categories: [{
      ordinal: 0,
      category_id: input.categoryId,
      display_name: `${input.categoryId}分类`,
    }],
    fields: [{
      ordinal: 0,
      category_id: input.categoryId,
      category_display_name: `${input.categoryId}分类`,
      field_id: input.fieldId,
      display_name: `${input.fieldId}字段`,
      knowledge_role: '事实 Fact',
      formation_modes: ['原文抽取'],
      output_kind: 'Fact',
      state: 'unknown',
      value: null,
      evidence: [],
    }],
    preview_sha256: H('b'),
  }
}

test('preview navigation is derived from class, product, category, and field payload order', () => {
  const medical = parseV5CandidatePreview(preview({
    insuranceClass: '医疗险',
    productId: 'medical-a',
    categoryId: '02',
    fieldId: 'medical_only',
  }))
  const annuity = parseV5CandidatePreview(preview({
    insuranceClass: '年金险',
    productId: 'annuity-b',
    categoryId: '11',
    fieldId: 'annuity_only',
  }))

  const navigation = projectV5PreviewNavigation([annuity, medical])

  assert.deepEqual(navigation.map(item => item.insurance_class), ['年金险', '医疗险'])
  assert.deepEqual(navigation[0]?.products[0]?.categories[0]?.fields.map(field => field.field_id), [
    'annuity_only',
  ])
  assert.deepEqual(navigation[1]?.products[0]?.categories[0]?.fields.map(field => field.field_id), [
    'medical_only',
  ])
})

test('closed preview parsing rejects serving authority and trailing data', () => {
  const exact = preview({
    insuranceClass: '医疗险',
    productId: 'medical-a',
    categoryId: '02',
    fieldId: 'product_name',
  })

  assert.throws(() => parseV5CandidatePreview({ ...exact, serving_effect: 'ACTIVE' }), {
    message: 'V5_PREVIEW_CONTRACT_INVALID',
  })
  assert.throws(() => parseV5CandidatePreview({ ...exact, active_release_id: 'forbidden' }), {
    message: 'V5_PREVIEW_CONTRACT_INVALID',
  })
  assert.throws(() => parseV5CandidatePreview({
    ...exact,
    fields: [{ ...exact.fields[0], state: 'unknown', value: 'forbidden' }],
  }), { message: 'V5_PREVIEW_CONTRACT_INVALID' })
})

test('preview parsing accepts sparse catalog ordinals but rejects reordered categories', () => {
  const exact = preview({
    insuranceClass: '两全保险',
    productId: 'endowment-a',
    categoryId: '02',
    fieldId: 'product_name',
  })
  const categories = [
    exact.categories[0],
    { ordinal: 2, category_id: '04', display_name: '04分类' },
  ]
  const fields = [
    exact.fields[0],
    {
      ...exact.fields[0],
      ordinal: 1,
      category_id: '04',
      category_display_name: '04分类',
      field_id: 'entry_age_range',
    },
  ]

  assert.equal(parseV5CandidatePreview({ ...exact, categories, fields }).categories[1]?.ordinal, 2)
  assert.throws(() => parseV5CandidatePreview({
    ...exact,
    categories: [categories[1], categories[0]],
    fields: [fields[1], fields[0]],
  }), { message: 'V5_PREVIEW_CONTRACT_INVALID' })
})
