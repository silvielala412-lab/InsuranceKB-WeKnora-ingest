// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { V5PreviewClient } from '../../../../api/schema-wiki/v5Preview.ts'
import V5SchemaPreview from './V5SchemaPreview.vue'
import { parseV5CandidatePreview } from '../../../../api/schema-wiki/v5/v5PreviewContract.ts'
import { parseV5ProviderTrialRun } from '../../../../api/schema-wiki/v5/v5ProviderTrialContract.ts'
import { parseV5SearchResult } from '../../../../api/schema-wiki/v5/v5SearchContract.ts'
import { providerRunFixture } from './v5ProviderTrialFixture.ts'

const H = (character: string) => character.repeat(64)

describe('V5SchemaPreview dynamic product rendering', () => {
  it('renders payload class, product, category, localized field, state, and role', async () => {
    const preview = parseV5CandidatePreview({
      contract: 'insurance-v5-candidate-preview.v2',
      catalog_id: 'insurance-product-schema-v5',
      catalog_sha256: H('a'),
      schema_id: 'insurance-product-schema-v5:医疗险',
      source_revision_id: 'source-medical-a',
      insurance_class: '医疗险',
      product_id: 'medical-a',
      product_version_id: 'medical-a@v1',
      product_display_name: '安心医疗险',
      serving_effect: 'NONE',
      review_publish_admission: false,
      categories: [{ ordinal: 0, category_id: '02', display_name: '产品主数据' }],
      fields: [{
        ordinal: 0,
        category_id: '02',
        category_display_name: '产品主数据',
        field_id: 'product_name',
        display_name: '险种名称',
        knowledge_role: '事实 Fact',
        formation_modes: ['原文抽取'],
        output_kind: 'Fact',
        state: 'present',
        value: '安心医疗险',
        evidence: [{
          source_revision_id: 'source-medical-a',
          verification_status: 'VERIFIED',
          verification_error: null,
          locator: 'page:1',
          quote: '产品名称：安心医疗险',
        }],
      }],
      preview_sha256: H('b'),
    })
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
            field_count: 1,
          }],
        }
      },
      async createPreview() {
        return preview
      },
      async getProviderRun() {
        return null
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
          answer: '检索到 1 条相关字段。',
          matches: [{
            product_id: 'medical-a',
            product_version_id: 'medical-a@v1',
            product_display_name: '安心医疗险',
            insurance_class: '医疗险',
            field_id: 'product_name',
            field_display_name: '险种名称',
            category_display_name: '产品主数据',
            value: '安心医疗险',
            score: 8,
            evidence: [{
              locator: 'page:1',
              quote: '产品名称：安心医疗险',
              verification_status: 'VERIFIED',
            }],
          }],
          provider_error: null,
        })
      },
    }

    const wrapper = mount(V5SchemaPreview, { props: { client } })
    await flushPromises()
    await wrapper.get('[data-testid="v5-run-preview"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('医疗险')
    expect(wrapper.text()).toContain('安心医疗险')
    expect(wrapper.text()).toContain('产品主数据')
    expect(wrapper.text()).toContain('险种名称')
    expect(wrapper.text()).toContain('已抽取')
    expect(wrapper.text()).toContain('事实 Fact')
    expect(wrapper.text()).toContain('产品名称：安心医疗险')

    await wrapper.get('[data-testid="v5-search-tab"]').trigger('click')
    await wrapper.get('[aria-label="搜索产品知识"]').setValue('险种名称')
    await wrapper.get('[data-testid="v5-search-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('产品知识搜索')
    expect(wrapper.text()).toContain('检索到 1 条相关字段。')
    expect(wrapper.text()).toContain('本地字段检索')
  })

  it('preloads completed real provider results without presenting Active authority', async () => {
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
        throw new Error('manual preview must not run during preload')
      },
      async getProviderRun() {
        return run
      },
      async runDynamicFieldGapfill() {
        throw new Error('not used')
      },
    }

    const wrapper = mount(V5SchemaPreview, { props: { client } })
    await flushPromises()

    expect(wrapper.text()).toContain('qwen-plus')
    expect(wrapper.text()).toContain('真实抽取')
    expect(wrapper.text()).toContain('平安e生保（尊享版）医疗保险')
    expect(wrapper.text()).toContain('1 次调用')
    expect(wrapper.find('[data-evidence-status="UNRESOLVED"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('V5_EVIDENCE_PAGE_NOT_FOUND')
    expect(wrapper.text()).not.toContain('Active Release')
  })
})
