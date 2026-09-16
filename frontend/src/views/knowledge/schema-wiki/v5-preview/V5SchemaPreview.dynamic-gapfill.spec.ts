// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { V5PreviewClient } from '../../../../api/schema-wiki/v5Preview.ts'
import V5SchemaPreview from './V5SchemaPreview.vue'
import { parseV5ProviderTrialRun } from '../../../../api/schema-wiki/v5/v5ProviderTrialContract.ts'
import { providerRunFixture } from './v5ProviderTrialFixture.ts'

const H = (character: string) => character.repeat(64)

function providerRunWithUnknown() {
  const fixture = providerRunFixture() as any
  const present = fixture.products[0].preview.fields[0]
  fixture.products[0].preview.fields.push({
    ...present,
    ordinal: 1,
    field_id: 'target_customer_profile',
    display_name: '适用人群',
    state: 'unknown',
    value: null,
    evidence: [],
  })
  return parseV5ProviderTrialRun(fixture)
}

describe('V5SchemaPreview dynamic field actions', () => {
  it('offers gapfill for unknown and review for resolved fields', async () => {
    const run = providerRunWithUnknown()
    const client = {
      async getCatalog() {
        return {
          catalog_id: 'insurance-product-schema-v5' as const,
          catalog_sha256: H('a'),
          source_sha256: H('c'),
          schemas: [{
            ordinal: 0,
            insurance_class: '医疗险',
            schema_id: 'insurance-product-schema-v5:医疗险',
            field_count: 67,
          }],
        }
      },
      async createPreview() {
        throw new Error('not used')
      },
      async getProviderRun() {
        return run
      },
      async runDynamicFieldGapfill() {
        throw new Error('not executed in rendering test')
      },
    } as V5PreviewClient
    const wrapper = mount(V5SchemaPreview, { props: { client } })
    await flushPromises()

    const unknownField = run.products[0]?.preview?.fields.find(field => field.state === 'unknown')
    const presentField = run.products[0]?.preview?.fields.find(field => field.state === 'present')
    expect(unknownField).toBeDefined()
    expect(presentField).toBeDefined()

    await wrapper.findAll('.v5-preview__field-link')
      .find(button => button.text().includes(unknownField!.display_name))!
      .trigger('click')
    expect(wrapper.get('[data-testid="v5-field-gapfill"]').text()).toContain('补抽')

    await wrapper.findAll('.v5-preview__field-link')
      .find(button => button.text().includes(presentField!.display_name))!
      .trigger('click')
    expect(wrapper.get('[data-testid="v5-field-review"]').text()).toContain('复核')
  })

  it('sends only candidate identity, action, and field ids', async () => {
    const run = providerRunWithUnknown()
    const preview = run.products[0]!.preview!
    const requests: unknown[] = []
    const client = {
      async getCatalog() {
        return {
          catalog_id: 'insurance-product-schema-v5' as const,
          catalog_sha256: H('a'),
          source_sha256: H('c'),
          schemas: [{
            ordinal: 0,
            insurance_class: '医疗险',
            schema_id: 'insurance-product-schema-v5:医疗险',
            field_count: 67,
          }],
        }
      },
      async createPreview() {
        throw new Error('not used')
      },
      async getProviderRun() {
        return run
      },
      async runDynamicFieldGapfill(request: unknown) {
        requests.push(request)
        return {
          contract: 'insurance-v5-dynamic-field-gapfill-response.v1',
          operation_id: 'dynamic-field-test',
          action: 'gapfill',
          status: 'NO_CHANGE',
          product_version_id: preview.product_version_id,
          base_preview_sha256: preview.preview_sha256,
          serving_effect: 'NONE',
          review_publish_admission: false,
          call_count: 0,
          stages: [{
            scope: 'matched_snippets',
            scanned_page_count: 1,
            selected_page_count: 0,
            context_sha256: H('f'),
            outcome: 'NO_CANDIDATE',
          }],
          fields: [{
            field_id: 'target_customer_profile',
            status: 'STILL_UNKNOWN',
            scope_used: null,
            changed: false,
            before: { state: 'unknown', value: null, evidence: [] },
            proposed: null,
            after: { state: 'unknown', value: null, evidence: [] },
          }],
          candidate_preview: preview,
        }
      },
    } as V5PreviewClient
    const wrapper = mount(V5SchemaPreview, { props: { client } })
    await flushPromises()
    await wrapper.findAll('.v5-preview__field-link')
      .find(button => button.text().includes('适用人群'))!
      .trigger('click')
    await wrapper.get('[data-testid="v5-field-gapfill"]').trigger('click')
    await flushPromises()

    expect(requests).toHaveLength(1)
    expect(Object.keys(requests[0] as Record<string, unknown>).sort()).toEqual([
      'action',
      'contract',
      'field_ids',
      'preview_sha256',
      'product_version_id',
    ])
    expect(requests[0]).not.toHaveProperty('source_text')
  })
})
