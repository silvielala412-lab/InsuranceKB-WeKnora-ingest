import assert from 'node:assert/strict'
import test from 'node:test'

import { providerRunFixture } from './v5ProviderTrialFixture.ts'
import { parseV5ProviderTrialRun } from '../../../../api/schema-wiki/v5/v5ProviderTrialContract.ts'

test('closed provider run exposes real preview and redacted receipts', () => {
  const run = parseV5ProviderTrialRun(providerRunFixture())

  assert.equal(run.provider.model, 'qwen-plus')
  assert.equal(run.products[0]?.status, 'REVIEW_REQUIRED')
  assert.equal(run.products[0]?.preview?.fields.length, 1)
  assert.equal(
    run.products[0]?.preview?.fields[0]?.evidence[0]?.verification_status,
    'UNRESOLVED',
  )
  assert.equal(run.products[0]?.attempts[0]?.total_tokens, 120)
})

test('provider run rejects active authority, trailing fields, and secret-shaped data', () => {
  const exact = providerRunFixture()
  assert.throws(() => parseV5ProviderTrialRun({ ...exact, serving_effect: 'ACTIVE' }), {
    message: 'V5_PROVIDER_TRIAL_CONTRACT_INVALID',
  })
  assert.throws(() => parseV5ProviderTrialRun({ ...exact, api_key: 'forbidden' }), {
    message: 'V5_PROVIDER_TRIAL_CONTRACT_INVALID',
  })
  assert.throws(() => parseV5ProviderTrialRun({
    ...exact,
    products: [{ ...exact.products[0], status: 'FAILED', preview: exact.products[0].preview }],
  }), { message: 'V5_PROVIDER_TRIAL_CONTRACT_INVALID' })
})

test('provider run preserves a primary preview after repair rejection', () => {
  const exact = providerRunFixture()
  const primary = exact.products[0]!.attempts[0]!
  const repairRejected = {
    attempt: 2,
    outcome: 'REPAIR_REJECTED',
    response_id: null,
    response_model: null,
    finish_reason: null,
    prompt_tokens: null,
    completion_tokens: null,
    total_tokens: null,
    error_code: 'LLM_RESULT_EMPTY',
  } as const
  const run = parseV5ProviderTrialRun({
    ...exact,
    call_count: 2,
    products: [{
      ...exact.products[0]!,
      attempts: [primary, repairRejected],
    }],
  })

  assert.equal(run.products[0]?.preview?.product_id, '596')
  assert.equal(run.products[0]?.attempts[1]?.outcome, 'REPAIR_REJECTED')
})

test('provider run admits the bounded Mission 127 four-attempt shape', () => {
  const exact = providerRunFixture()
  const attempts = [1, 2, 3, 4].map(attempt => ({
    ...exact.products[0]!.attempts[0]!,
    attempt,
  }))
  const run = parseV5ProviderTrialRun({
    ...exact,
    call_count: 4,
    products: [{ ...exact.products[0]!, attempts }],
  })

  assert.equal(run.products[0]?.attempts.length, 4)
})

test('provider run admits the bounded Mission 139 nine-product shape', () => {
  const exact = providerRunFixture()
  const base = exact.products[0]!
  const products = Array.from({ length: 9 }, (_, index) => {
    const productId = `${9000 + index}`
    const productVersionId = `${productId}-1`
    const sourceRevisionId = `source-m139-${productVersionId}`
    return {
      ...base,
      product_id: productId,
      product_version_id: productVersionId,
      product_display_name: `M139 产品 ${index + 1}`,
      source_revision_id: sourceRevisionId,
      attempts: [1, 2].map(attempt => ({
        ...base.attempts[0]!,
        attempt,
        response_id: `chatcmpl-m139-${index + 1}-${attempt}`,
      })),
      preview: {
        ...base.preview,
        product_id: productId,
        product_version_id: productVersionId,
        product_display_name: `M139 产品 ${index + 1}`,
        source_revision_id: sourceRevisionId,
        fields: base.preview.fields.map(field => ({
          ...field,
          value: `M139 产品 ${index + 1}`,
          evidence: field.evidence.map(evidence => ({
            ...evidence,
            source_revision_id: sourceRevisionId,
          })),
        })),
      },
    }
  })
  const run = parseV5ProviderTrialRun({ ...exact, call_count: 18, products })

  assert.equal(run.products.length, 9)
  assert.equal(run.call_count, 18)
})

test('provider run admits the Mission 159 32-call microbatch envelope only', () => {
  const exact = providerRunFixture()
  const base = exact.products[0]!
  const attemptCounts = [6, 3, 3, 3, 8, 9]
  const products = attemptCounts.map((attemptCount, index) => {
    const productId = `${9500 + index}`
    const productVersionId = `${productId}-1`
    const sourceRevisionId = `source-m159-${productVersionId}`
    return {
      ...base,
      product_id: productId,
      product_version_id: productVersionId,
      product_display_name: `M159 产品 ${index + 1}`,
      source_revision_id: sourceRevisionId,
      attempts: Array.from({ length: attemptCount }, (_, attemptIndex) => ({
        ...base.attempts[0]!,
        attempt: attemptIndex + 1,
        response_id: `chatcmpl-m159-${index + 1}-${attemptIndex + 1}`,
      })),
      preview: {
        ...base.preview,
        product_id: productId,
        product_version_id: productVersionId,
        product_display_name: `M159 产品 ${index + 1}`,
        source_revision_id: sourceRevisionId,
        fields: base.preview.fields.map(field => ({
          ...field,
          value: `M159 产品 ${index + 1}`,
          evidence: field.evidence.map(evidence => ({
            ...evidence,
            source_revision_id: sourceRevisionId,
          })),
        })),
      },
    }
  })

  const run = parseV5ProviderTrialRun({ ...exact, call_count: 32, products })
  assert.deepEqual(run.products.map(product => product.attempts.length), attemptCounts)
  assert.equal(run.call_count, 32)

  const thirtyThirdAttempt = {
    ...products[0]!.attempts.at(-1)!,
    attempt: products[0]!.attempts.length + 1,
  }
  assert.throws(() => parseV5ProviderTrialRun({
    ...exact,
    call_count: 33,
    products: [{
      ...products[0]!,
      attempts: [...products[0]!.attempts, thirtyThirdAttempt],
    }, ...products.slice(1)],
  }), { message: 'V5_PROVIDER_TRIAL_CONTRACT_INVALID' })
})

test('provider run admits Mission 142 material support diagnostics', () => {
  const exact = providerRunFixture()
  const product = exact.products[0]!
  const run = parseV5ProviderTrialRun({
    ...exact,
    products: [{
      ...product,
      material_support: [{
        field_id: 'target_customer_profile',
        status: 'supported',
        basis: '材料页面出现适用人群语义',
        candidate_locators: ['pdf:产品说明书.pdf#page=1'],
      }],
      material_support_metrics: {
        extractable_field_count: 1,
        material_supported_field_count: 1,
        material_supported_present_count: 1,
        rate: 1,
        ambiguous_field_count: 0,
        unsupported_field_count: 0,
      },
    }],
  })

  assert.equal(run.products[0]?.material_support_metrics?.rate, 1)
  assert.equal(run.products[0]?.material_support[0]?.status, 'supported')
})
