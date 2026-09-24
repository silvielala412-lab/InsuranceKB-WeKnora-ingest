// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { V5PreviewClient } from '../../../../api/schema-wiki/v5Preview.ts'
import { parseV5ProviderTrialRun } from '../../../../api/schema-wiki/v5/v5ProviderTrialContract.ts'
import { parseV5SearchResult } from '../../../../api/schema-wiki/v5/v5SearchContract.ts'
import V5SchemaPreview from './V5SchemaPreview.vue'
import { providerRunFixture } from './v5ProviderTrialFixture.ts'

const H = (character: string) => character.repeat(64)

describe('V5SchemaPreview tabs', () => {
  it('opens the Q&A tab and returns to the field when a result is opened', async () => {
    const run = parseV5ProviderTrialRun(providerRunFixture())
    const client: V5PreviewClient = {
      async getCatalog() {
        return {
          catalog_id: 'insurance-product-schema-v5',
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
        throw new Error('not used')
      },
      async search() {
        return parseV5SearchResult({
          contract: 'insurance-v5-search-response.v1',
          query: '险种名称',
          provider: 'local',
          model: null,
          answer: '平安e生保的险种名称已命中。',
          matches: [{
            product_id: '596',
            product_version_id: '596-1',
            product_display_name: '平安e生保（尊享版）医疗保险',
            insurance_class: '医疗险',
            field_id: 'product_name',
            field_display_name: '险种名称',
            category_display_name: '产品主数据',
            value: '平安e生保（尊享版）医疗保险',
            score: 8,
            evidence: [{
              locator: 'pdf:保险条款.pdf#page=1',
              quote: '平安e生保（尊享版）医疗保险',
              verification_status: 'UNRESOLVED',
            }],
          }],
          provider_error: null,
        })
      },
    }

    const wrapper = mount(V5SchemaPreview, { props: { client } })
    await flushPromises()
    await wrapper.get('[data-testid="v5-search-tab"]').trigger('click')
    expect(wrapper.find('[data-testid="v5-qa-tab"]').exists()).toBe(true)

    await wrapper.get('[aria-label="搜索产品知识"]').setValue('险种名称')
    await wrapper.get('[data-testid="v5-search-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('平安e生保的险种名称已命中。')

    await wrapper.get('.v5-preview__search-open').trigger('click')
    expect(wrapper.get('[data-testid="v5-preview-tab"]').attributes('aria-selected')).toBe('true')
    expect(wrapper.text()).toContain('险种名称')
  })
})
