<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import {
  createV5PreviewClient,
  type V5CatalogIndex,
  type V5PreviewClient,
  type V5PreviewRequest,
} from '../../../../api/schema-wiki/v5Preview.ts'
import {
  projectV5PreviewNavigation,
  type V5CandidatePreview,
  type V5EvidenceVerificationStatus,
  type V5PreviewField,
} from './v5PreviewContract.ts'
import type { V5ProviderTrialRun } from './v5ProviderTrialContract.ts'
import type {
  V5DynamicFieldAction,
  V5DynamicFieldDiff,
  V5DynamicFieldGapfillResponse,
} from './v5DynamicGapfillContract.ts'

const props = withDefaults(defineProps<{ client?: V5PreviewClient }>(), {
  client: () => createV5PreviewClient(),
})

const catalog = ref<V5CatalogIndex | null>(null)
const previews = ref<V5CandidatePreview[]>([])
const providerRun = ref<V5ProviderTrialRun | null>(null)
const loadingCatalog = ref(true)
const running = ref(false)
const runningFieldAction = ref(false)
const errorMessage = ref('')
const dynamicResult = ref<V5DynamicFieldGapfillResponse | null>(null)
const selectedProductVersionId = ref('')
const selectedFieldId = ref('')

const form = reactive({
  mode: 'fixture' as 'fixture' | 'llm',
  insuranceClass: '',
  productDisplayName: '待抽取产品',
  productId: 'preview-product-1',
  productVersionId: 'preview-product-1@v1',
  sourceRevisionId: 'source-revision-1',
  sourceText: '',
})

const selectedSchema = computed(() => catalog.value?.schemas.find(
  schema => schema.insurance_class === form.insuranceClass,
) ?? null)
const navigation = computed(() => projectV5PreviewNavigation(previews.value))
const selectedPreview = computed(() => previews.value.find(
  preview => preview.product_version_id === selectedProductVersionId.value,
) ?? previews.value[0] ?? null)
const selectedField = computed(() => selectedPreview.value?.fields.find(
  field => field.field_id === selectedFieldId.value,
) ?? selectedPreview.value?.fields[0] ?? null)
const selectedDynamicDiff = computed<V5DynamicFieldDiff | null>(() => (
  dynamicResult.value?.product_version_id === selectedPreview.value?.product_version_id
    ? dynamicResult.value.fields.find(field => field.field_id === selectedField.value?.field_id) ?? null
    : null
))
const fieldMetrics = computed(() => {
  const fields = selectedPreview.value?.fields ?? []
  return {
    total: fields.length,
    present: fields.filter(field => field.state === 'present').length,
    absent: fields.filter(field => field.state === 'absent_explicitly').length,
    unknown: fields.filter(field => field.state === 'unknown').length,
  }
})
const evidenceMetrics = computed(() => {
  const evidence = (selectedPreview.value?.fields ?? []).flatMap(field => field.evidence)
  return {
    total: evidence.length,
    verified: evidence.filter(item => item.verification_status === 'VERIFIED').length,
    normalized: evidence.filter(item => item.verification_status === 'NORMALIZED_MATCH').length,
    unresolved: evidence.filter(item => item.verification_status === 'UNRESOLVED').length,
    ambiguous: evidence.filter(item => item.verification_status === 'AMBIGUOUS').length,
  }
})
const providerDataCount = computed(() => providerRun.value?.products.filter(
  product => product.preview !== null,
).length ?? 0)
const providerReviewProducts = computed(() => providerRun.value?.products.filter(
  product => product.status === 'REVIEW_REQUIRED',
) ?? [])
const providerRepairProducts = computed(() => providerRun.value?.products.filter(
  product => product.attempts.length > 1,
) ?? [])
const providerFailures = computed(() => providerRun.value?.products.filter(
  product => product.status === 'FAILED',
) ?? [])

const stateLabels: Record<V5PreviewField['state'], string> = {
  present: '已抽取',
  absent_explicitly: '原文明示无',
  unknown: '待补充',
}

const evidenceStatusLabels: Record<V5EvidenceVerificationStatus, string> = {
  VERIFIED: '已核验',
  NORMALIZED_MATCH: '归一化匹配',
  UNRESOLVED: '未定位',
  AMBIGUOUS: '多处匹配',
}
const dynamicFieldStatusLabels: Record<V5DynamicFieldDiff['status'], string> = {
  FILLED: '已补抽',
  CONFIRMED: '已复核',
  CONFLICT: '发现冲突',
  STILL_UNKNOWN: '仍待补充',
  UNCHANGED: '未变化',
}
const dynamicScopeLabels = {
  matched_snippets: '首轮候选片段',
  adjacent_pages: '相邻页面',
  all_material: '全材料页面',
} as const

function formatValue(value: V5PreviewField['value']): string {
  if (Array.isArray(value)) return value.join('、')
  return value === null ? '' : String(value)
}

function selectProduct(preview: V5CandidatePreview): void {
  selectedProductVersionId.value = preview.product_version_id
  selectedFieldId.value = preview.fields[0]?.field_id ?? ''
}

function selectField(preview: V5CandidatePreview, fieldId: string): void {
  selectedProductVersionId.value = preview.product_version_id
  selectedFieldId.value = fieldId
}

function clearPreviews(): void {
  previews.value = []
  selectedProductVersionId.value = ''
  selectedFieldId.value = ''
  errorMessage.value = ''
  dynamicResult.value = null
}

async function runFieldAction(action: V5DynamicFieldAction): Promise<void> {
  const preview = selectedPreview.value
  const field = selectedField.value
  if (!preview || !field) return
  if (
    (action === 'gapfill' && field.state !== 'unknown')
    || (action === 'review' && field.state === 'unknown')
  ) {
    errorMessage.value = 'V5_DYNAMIC_FIELD_ACTION_INVALID'
    return
  }
  runningFieldAction.value = true
  errorMessage.value = ''
  try {
    const result = await props.client.runDynamicFieldGapfill({
      contract: 'insurance-v5-dynamic-field-gapfill-request.v1',
      product_version_id: preview.product_version_id,
      preview_sha256: preview.preview_sha256,
      action,
      field_ids: [field.field_id],
    })
    previews.value = previews.value.map(item => (
      item.product_version_id === result.product_version_id
        ? result.candidate_preview
        : item
    ))
    dynamicResult.value = result
    selectedProductVersionId.value = result.product_version_id
    selectedFieldId.value = field.field_id
  } catch (error) {
    errorMessage.value = error instanceof Error
      ? error.message
      : 'V5_DYNAMIC_FIELD_ACTION_FAILED'
  } finally {
    runningFieldAction.value = false
  }
}

async function loadCatalog(): Promise<void> {
  loadingCatalog.value = true
  errorMessage.value = ''
  try {
    catalog.value = await props.client.getCatalog()
    form.insuranceClass = catalog.value.schemas[0]?.insurance_class ?? ''
    providerRun.value = await props.client.getProviderRun()
    const completed = providerRun.value?.products.flatMap(
      product => product.preview === null ? [] : [product.preview],
    ) ?? []
    if (completed.length) {
      previews.value = completed
      selectProduct(completed[0] as V5CandidatePreview)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'V5_CATALOG_LOAD_FAILED'
  } finally {
    loadingCatalog.value = false
  }
}

async function runPreview(): Promise<void> {
  const schema = selectedSchema.value
  if (!schema || !form.productDisplayName.trim() || !form.productId.trim()
    || !form.productVersionId.trim() || !form.sourceRevisionId.trim()) {
    errorMessage.value = 'PREVIEW_IDENTITY_REQUIRED'
    return
  }
  if (form.mode === 'llm' && !form.sourceText.trim()) {
    errorMessage.value = 'LLM_SOURCE_TEXT_REQUIRED'
    return
  }
  running.value = true
  errorMessage.value = ''
  const request: V5PreviewRequest = {
    source_revision_id: form.sourceRevisionId.trim(),
    catalog_id: 'insurance-product-schema-v5',
    schema_id: schema.schema_id,
    product_id: form.productId.trim(),
    product_version_id: form.productVersionId.trim(),
    product_display_name: form.productDisplayName.trim(),
    reviewed_insurance_class: schema.insurance_class,
    classification: null,
    source_text: form.sourceText,
  }
  try {
    const preview = await props.client.createPreview(form.mode, request)
    const existingIndex = previews.value.findIndex(
      item => item.product_version_id === preview.product_version_id,
    )
    if (existingIndex >= 0) {
      previews.value = previews.value.map((item, index) => index === existingIndex ? preview : item)
    } else {
      previews.value = [...previews.value, preview]
    }
    selectProduct(preview)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'V5_PREVIEW_FAILED'
  } finally {
    running.value = false
  }
}

watch(() => form.insuranceClass, insuranceClass => {
  if (!insuranceClass || form.productDisplayName !== '待抽取产品') return
  form.productDisplayName = `${insuranceClass}待抽取产品`
})

onMounted(loadCatalog)
</script>

<template>
  <section class="v5-preview" data-testid="v5-schema-preview">
    <header class="v5-preview__toolbar">
      <div class="v5-preview__heading">
        <div>
          <h2>V5 Schema 抽取预览</h2>
          <span v-if="catalog" class="v5-preview__catalog-id">{{ catalog.catalog_sha256.slice(0, 12) }}</span>
        </div>
        <span class="v5-preview__authority">非发布候选</span>
      </div>

      <div class="v5-preview__mode" role="group" aria-label="抽取模式">
        <button type="button" :class="{ active: form.mode === 'fixture' }" @click="form.mode = 'fixture'">
          Fixture
        </button>
        <button type="button" :class="{ active: form.mode === 'llm' }" @click="form.mode = 'llm'">
          Qwen / MiniMax
        </button>
      </div>

      <button
        type="button"
        class="v5-preview__clear"
        title="清空预览"
        aria-label="清空预览"
        :disabled="previews.length === 0"
        @click="clearPreviews"
      >
        <t-icon name="delete" />
      </button>
      <button
        type="button"
        class="v5-preview__run"
        data-testid="v5-run-preview"
        :disabled="running || loadingCatalog || !selectedSchema"
        @click="runPreview"
      >
        <t-icon name="play-circle" />
        {{ running ? '抽取中' : '生成预览' }}
      </button>
    </header>

    <form class="v5-preview__form" @submit.prevent="runPreview">
      <label>
        <span>险种 Schema</span>
        <select v-model="form.insuranceClass" :disabled="loadingCatalog">
          <option
            v-for="schema in catalog?.schemas ?? []"
            :key="schema.schema_id"
            :value="schema.insurance_class"
          >
            {{ schema.insurance_class }} · {{ schema.field_count }} 字段
          </option>
        </select>
      </label>
      <label>
        <span>产品名称</span>
        <input v-model.trim="form.productDisplayName" type="text" />
      </label>
      <label>
        <span>产品 ID</span>
        <input v-model.trim="form.productId" type="text" />
      </label>
      <label>
        <span>产品版本</span>
        <input v-model.trim="form.productVersionId" type="text" />
      </label>
      <label>
        <span>来源版本</span>
        <input v-model.trim="form.sourceRevisionId" type="text" />
      </label>
      <label v-if="form.mode === 'llm'" class="v5-preview__source">
        <span>解析文本</span>
        <textarea v-model="form.sourceText" rows="5" />
      </label>
    </form>

    <section v-if="providerRun" class="v5-preview__provider-run" data-testid="v5-provider-run">
      <div>
        <strong>真实抽取</strong>
        <span>{{ providerRun.provider.model }}</span>
        <span>{{ providerRun.call_count }} 次调用</span>
        <span>{{ providerDataCount }}/{{ providerRun.products.length }} 款已有数据</span>
        <span v-if="providerRepairProducts.length">
          {{ providerRepairProducts.length }} 款已执行分类抽取/定向补抽
        </span>
        <span v-if="providerReviewProducts.length">
          {{ providerReviewProducts.length }} 款 Evidence 待核验
        </span>
        <code>{{ providerRun.run_sha256.slice(0, 12) }}</code>
      </div>
      <ul v-if="providerFailures.length">
        <li v-for="product in providerFailures" :key="product.product_version_id">
          {{ product.product_display_name }} · {{ product.error_code }}
        </li>
      </ul>
      <ul v-if="providerReviewProducts.length" class="v5-preview__review-list">
        <li v-for="product in providerReviewProducts" :key="product.product_version_id">
          {{ product.product_display_name }} · 数据已保留，Evidence 待核验
        </li>
      </ul>
    </section>

    <p v-if="errorMessage" class="v5-preview__error" role="alert">{{ errorMessage }}</p>

    <div v-if="previews.length" class="v5-preview__browser">
      <aside class="v5-preview__navigation">
        <section v-for="insurance in navigation" :key="insurance.insurance_class">
          <h3>{{ insurance.insurance_class }}</h3>
          <div v-for="product in insurance.products" :key="product.product_version_id">
            <button
              type="button"
              class="v5-preview__product"
              :class="{ active: selectedProductVersionId === product.product_version_id }"
              @click="selectProduct(product.preview)"
            >
              <span>{{ product.product_display_name }}</span>
              <small>{{ product.preview.fields.length }}</small>
            </button>
            <div v-if="selectedProductVersionId === product.product_version_id">
              <div v-for="category in product.categories" :key="category.category_id" class="v5-preview__category">
                <h4><span>{{ category.category_id }}</span>{{ category.display_name }}</h4>
                <button
                  v-for="field in category.fields"
                  :key="field.field_id"
                  type="button"
                  class="v5-preview__field-link"
                  :class="{ active: selectedFieldId === field.field_id }"
                  @click="selectField(product.preview, field.field_id)"
                >
                  <span class="v5-preview__state-dot" :data-state="field.state" />
                  <span>{{ field.display_name }}</span>
                  <small>{{ field.output_kind }}</small>
                </button>
              </div>
            </div>
          </div>
        </section>
      </aside>

      <main v-if="selectedPreview && selectedField" class="v5-preview__content">
        <div class="v5-preview__summary">
          <span>字段 <strong>{{ fieldMetrics.total }}</strong></span>
          <span>已抽取 <strong>{{ fieldMetrics.present }}</strong></span>
          <span>明示无 <strong>{{ fieldMetrics.absent }}</strong></span>
          <span>待补充 <strong>{{ fieldMetrics.unknown }}</strong></span>
          <span>Evidence <strong>{{ evidenceMetrics.total }}</strong></span>
          <span>已核验 <strong>{{ evidenceMetrics.verified }}</strong></span>
          <span>归一化 <strong>{{ evidenceMetrics.normalized }}</strong></span>
          <span>未定位 <strong>{{ evidenceMetrics.unresolved }}</strong></span>
          <span>多处匹配 <strong>{{ evidenceMetrics.ambiguous }}</strong></span>
        </div>

        <article class="v5-preview__field">
          <header>
            <div>
              <p>{{ selectedField.category_id }} · {{ selectedField.category_display_name }}</p>
              <h3>{{ selectedField.display_name }}</h3>
              <code>{{ selectedField.field_id }}</code>
            </div>
            <div class="v5-preview__field-actions">
              <span class="v5-preview__state" :data-state="selectedField.state">
                {{ stateLabels[selectedField.state] }}
              </span>
              <button
                v-if="selectedField.state === 'unknown'"
                type="button"
                data-testid="v5-field-gapfill"
                :disabled="runningFieldAction"
                @click="runFieldAction('gapfill')"
              >
                <t-icon name="search" />
                {{ runningFieldAction ? '处理中' : '补抽' }}
              </button>
              <button
                v-else
                type="button"
                data-testid="v5-field-review"
                :disabled="runningFieldAction"
                @click="runFieldAction('review')"
              >
                <t-icon name="check-circle" />
                {{ runningFieldAction ? '处理中' : '复核' }}
              </button>
            </div>
          </header>

          <div
            v-if="selectedDynamicDiff"
            class="v5-preview__dynamic-result"
            :data-status="selectedDynamicDiff.status"
          >
            <strong>{{ dynamicFieldStatusLabels[selectedDynamicDiff.status] }}</strong>
            <span v-if="selectedDynamicDiff.scope_used">
              {{ dynamicScopeLabels[selectedDynamicDiff.scope_used] }}
            </span>
            <span>{{ dynamicResult?.call_count ?? 0 }} 次调用</span>
            <code>{{ dynamicResult?.operation_id }}</code>
          </div>

          <dl class="v5-preview__metadata">
            <div>
              <dt>知识角色</dt>
              <dd><span :data-kind="selectedField.output_kind">{{ selectedField.knowledge_role }}</span></dd>
            </div>
            <div>
              <dt>形成方式</dt>
              <dd>{{ selectedField.formation_modes.join(' · ') }}</dd>
            </div>
            <div>
              <dt>产品版本</dt>
              <dd>{{ selectedPreview.product_version_id }}</dd>
            </div>
            <div>
              <dt>Schema</dt>
              <dd>{{ selectedPreview.schema_id }}</dd>
            </div>
          </dl>

          <section class="v5-preview__value">
            <h4>字段值</h4>
            <p v-if="selectedField.state === 'present'">{{ formatValue(selectedField.value) }}</p>
            <p v-else class="v5-preview__empty">{{ stateLabels[selectedField.state] }}</p>
          </section>

          <section class="v5-preview__evidence">
            <h4>Evidence <span>{{ selectedField.evidence.length }}</span></h4>
            <ol v-if="selectedField.evidence.length">
              <li v-for="evidence in selectedField.evidence" :key="`${evidence.locator}:${evidence.quote}`">
                <div class="v5-preview__evidence-head">
                  <code>{{ evidence.locator }}</code>
                  <span
                    class="v5-preview__evidence-status"
                    :data-evidence-status="evidence.verification_status"
                  >
                    {{ evidenceStatusLabels[evidence.verification_status] }}
                  </span>
                </div>
                <blockquote>{{ evidence.quote }}</blockquote>
                <small v-if="evidence.verification_error">{{ evidence.verification_error }}</small>
              </li>
            </ol>
            <p v-else class="v5-preview__empty">无 Evidence</p>
          </section>
        </article>
      </main>
    </div>

    <div v-else class="v5-preview__empty-workspace">
      <p v-if="loadingCatalog">正在加载 V5 Schema…</p>
      <div v-else-if="catalog" class="v5-preview__schema-grid">
        <button
          v-for="schema in catalog.schemas"
          :key="schema.schema_id"
          type="button"
          :class="{ active: form.insuranceClass === schema.insurance_class }"
          @click="form.insuranceClass = schema.insurance_class"
        >
          <span>{{ schema.insurance_class }}</span>
          <strong>{{ schema.field_count }}</strong>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.v5-preview { display: flex; flex-direction: column; height: 100%; min-height: 0; background: var(--td-bg-color-container); color: var(--td-text-color-primary); }
.v5-preview__toolbar { display: grid; grid-template-columns: minmax(220px, 1fr) auto 36px auto; gap: 10px; align-items: center; padding: 14px 20px; border-bottom: 1px solid var(--td-component-border); }
.v5-preview__heading { display: flex; align-items: center; gap: 12px; min-width: 0; }
.v5-preview__heading > div { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.v5-preview__heading h2 { margin: 0; font-size: 17px; line-height: 24px; letter-spacing: 0; }
.v5-preview__catalog-id { color: var(--td-text-color-placeholder); font-family: ui-monospace, monospace; font-size: 11px; }
.v5-preview__authority { flex: none; padding: 3px 7px; border: 1px solid var(--td-warning-color-4); border-radius: 4px; background: var(--td-warning-color-1); color: var(--td-warning-color-8); font-size: 12px; }
.v5-preview__mode { display: grid; grid-template-columns: 1fr 1fr; padding: 2px; border-radius: 6px; background: var(--td-bg-color-secondarycontainer); }
.v5-preview__mode button { min-width: 88px; height: 30px; border: 0; border-radius: 4px; background: transparent; color: var(--td-text-color-secondary); cursor: pointer; }
.v5-preview__mode button.active { background: var(--td-bg-color-container); color: var(--td-text-color-primary); box-shadow: var(--td-shadow-1); }
.v5-preview__clear, .v5-preview__run { height: 34px; border-radius: 5px; cursor: pointer; }
.v5-preview__clear { width: 36px; border: 1px solid var(--td-component-border); background: transparent; color: var(--td-text-color-secondary); }
.v5-preview__run { display: inline-flex; align-items: center; gap: 6px; padding: 0 14px; border: 1px solid var(--td-brand-color); background: var(--td-brand-color); color: #fff; }
.v5-preview__clear:disabled, .v5-preview__run:disabled { cursor: not-allowed; opacity: .45; }
.v5-preview__form { display: grid; grid-template-columns: minmax(180px, 1.2fr) repeat(4, minmax(140px, 1fr)); gap: 10px; padding: 12px 20px; border-bottom: 1px solid var(--td-component-border); background: var(--td-bg-color-secondarycontainer); }
.v5-preview__form label { display: grid; gap: 5px; min-width: 0; }
.v5-preview__form label > span { color: var(--td-text-color-secondary); font-size: 12px; }
.v5-preview__form input, .v5-preview__form select, .v5-preview__form textarea { box-sizing: border-box; width: 100%; min-width: 0; border: 1px solid var(--td-component-border); border-radius: 5px; background: var(--td-bg-color-container); color: var(--td-text-color-primary); font: inherit; }
.v5-preview__form input, .v5-preview__form select { height: 34px; padding: 0 9px; }
.v5-preview__form textarea { padding: 9px; resize: vertical; line-height: 1.5; }
.v5-preview__source { grid-column: 1 / -1; }
.v5-preview__error { margin: 0; padding: 8px 20px; border-bottom: 1px solid var(--td-error-color-3); background: var(--td-error-color-1); color: var(--td-error-color-7); font-size: 13px; }
.v5-preview__provider-run { display: grid; gap: 6px; padding: 9px 20px; border-bottom: 1px solid var(--td-component-border); background: var(--td-success-color-1); color: var(--td-text-color-secondary); font-size: 12px; }
.v5-preview__provider-run > div { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; }
.v5-preview__provider-run strong { color: var(--td-success-color-7); }
.v5-preview__provider-run code { color: var(--td-text-color-placeholder); font-family: ui-monospace, monospace; }
.v5-preview__provider-run ul { display: flex; flex-wrap: wrap; gap: 8px 20px; margin: 0; padding: 0; color: var(--td-error-color-7); list-style: none; }
.v5-preview__provider-run .v5-preview__review-list { color: var(--td-warning-color-8); }
.v5-preview__browser { display: grid; grid-template-columns: 310px minmax(0, 1fr); flex: 1; min-height: 0; }
.v5-preview__navigation { overflow: auto; padding: 16px 12px 28px; border-right: 1px solid var(--td-component-border); }
.v5-preview__navigation h3 { margin: 8px 8px 6px; font-size: 13px; letter-spacing: 0; }
.v5-preview__product, .v5-preview__field-link { display: grid; width: 100%; border: 0; background: transparent; text-align: left; cursor: pointer; }
.v5-preview__product { grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; padding: 8px; border-radius: 5px; font-weight: 600; }
.v5-preview__product.active { background: var(--td-brand-color-light); color: var(--td-brand-color); }
.v5-preview__product span, .v5-preview__field-link span { min-width: 0; overflow-wrap: anywhere; }
.v5-preview__product small { color: var(--td-text-color-placeholder); }
.v5-preview__category { padding: 5px 0 8px 12px; }
.v5-preview__category h4 { display: flex; gap: 6px; margin: 8px 4px 4px; color: var(--td-text-color-secondary); font-size: 12px; font-weight: 500; letter-spacing: 0; }
.v5-preview__category h4 span { color: var(--td-text-color-placeholder); font-family: ui-monospace, monospace; }
.v5-preview__field-link { grid-template-columns: 8px minmax(0, 1fr) auto; gap: 7px; align-items: center; padding: 6px 7px; border-radius: 4px; color: var(--td-text-color-secondary); font-size: 13px; }
.v5-preview__field-link.active { background: var(--td-bg-color-secondarycontainer-hover); color: var(--td-text-color-primary); }
.v5-preview__field-link small { color: var(--td-text-color-placeholder); font-size: 10px; }
.v5-preview__state-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--td-text-color-disabled); }
.v5-preview__state-dot[data-state='present'] { background: var(--td-success-color); }
.v5-preview__state-dot[data-state='absent_explicitly'] { background: var(--td-warning-color); }
.v5-preview__content { min-width: 0; overflow: auto; padding: 0 28px 40px; }
.v5-preview__summary { position: sticky; top: 0; z-index: 1; display: flex; flex-wrap: wrap; gap: 22px; margin: 0 -28px 28px; padding: 11px 28px; border-bottom: 1px solid var(--td-component-border); background: var(--td-bg-color-container); color: var(--td-text-color-secondary); font-size: 12px; }
.v5-preview__summary strong { margin-left: 4px; color: var(--td-text-color-primary); }
.v5-preview__field { max-width: 920px; margin: 0 auto; }
.v5-preview__field > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; }
.v5-preview__field-actions { display: flex; align-items: center; gap: 8px; }
.v5-preview__field-actions button { display: inline-flex; align-items: center; gap: 5px; height: 30px; padding: 0 10px; border: 1px solid var(--td-brand-color); border-radius: 4px; background: var(--td-brand-color); color: #fff; cursor: pointer; }
.v5-preview__field-actions button:disabled { cursor: not-allowed; opacity: .45; }
.v5-preview__dynamic-result { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 18px; padding: 9px 12px; border-left: 3px solid var(--td-brand-color); background: var(--td-bg-color-secondarycontainer); color: var(--td-text-color-secondary); font-size: 12px; }
.v5-preview__dynamic-result[data-status='CONFLICT'] { border-left-color: var(--td-warning-color); }
.v5-preview__dynamic-result strong { color: var(--td-text-color-primary); }
.v5-preview__dynamic-result code { margin-left: auto; }
.v5-preview__field header p { margin: 0 0 5px; color: var(--td-text-color-placeholder); font-size: 12px; }
.v5-preview__field h3 { margin: 0 0 5px; font-size: 24px; letter-spacing: 0; overflow-wrap: anywhere; }
.v5-preview__field code { color: var(--td-text-color-placeholder); font-family: ui-monospace, monospace; font-size: 12px; overflow-wrap: anywhere; }
.v5-preview__state { flex: none; padding: 5px 9px; border-radius: 4px; background: var(--td-bg-color-secondarycontainer); color: var(--td-text-color-secondary); font-size: 12px; }
.v5-preview__state[data-state='present'] { background: var(--td-success-color-1); color: var(--td-success-color-7); }
.v5-preview__state[data-state='absent_explicitly'] { background: var(--td-warning-color-1); color: var(--td-warning-color-8); }
.v5-preview__metadata { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 28px 0; border-top: 1px solid var(--td-component-border); border-bottom: 1px solid var(--td-component-border); }
.v5-preview__metadata div { display: grid; grid-template-columns: 82px minmax(0, 1fr); gap: 12px; padding: 11px 0; }
.v5-preview__metadata div:nth-child(odd) { padding-right: 24px; }
.v5-preview__metadata dt { color: var(--td-text-color-placeholder); font-size: 12px; }
.v5-preview__metadata dd { min-width: 0; margin: 0; color: var(--td-text-color-secondary); overflow-wrap: anywhere; }
.v5-preview__metadata [data-kind] { display: inline-block; padding: 2px 6px; border-radius: 4px; background: var(--td-bg-color-secondarycontainer); }
.v5-preview__metadata [data-kind='Fact'] { border-left: 3px solid var(--td-brand-color); }
.v5-preview__metadata [data-kind='Relation'] { border-left: 3px solid var(--td-warning-color); }
.v5-preview__metadata [data-kind='Derived'] { border-left: 3px solid var(--td-success-color); }
.v5-preview__metadata [data-kind='Content'] { border-left: 3px solid var(--td-error-color-5); }
.v5-preview__value, .v5-preview__evidence { padding: 4px 0 22px; }
.v5-preview__value h4, .v5-preview__evidence h4 { margin: 0 0 10px; font-size: 13px; letter-spacing: 0; }
.v5-preview__value > p:not(.v5-preview__empty) { margin: 0; padding: 14px 16px; border-left: 3px solid var(--td-brand-color); background: var(--td-bg-color-secondarycontainer); white-space: pre-wrap; line-height: 1.65; overflow-wrap: anywhere; }
.v5-preview__evidence h4 span { color: var(--td-text-color-placeholder); font-weight: 400; }
.v5-preview__evidence ol { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.v5-preview__evidence li { padding: 12px 14px; border: 1px solid var(--td-component-border); border-radius: 6px; }
.v5-preview__evidence-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.v5-preview__evidence-status { flex: none; padding: 2px 6px; border-radius: 4px; background: var(--td-success-color-1); color: var(--td-success-color-7); font-size: 11px; }
.v5-preview__evidence-status[data-evidence-status='NORMALIZED_MATCH'] { background: var(--td-brand-color-light); color: var(--td-brand-color); }
.v5-preview__evidence-status[data-evidence-status='UNRESOLVED'], .v5-preview__evidence-status[data-evidence-status='AMBIGUOUS'] { background: var(--td-warning-color-1); color: var(--td-warning-color-8); }
.v5-preview__evidence blockquote { margin: 8px 0 0; color: var(--td-text-color-secondary); line-height: 1.6; overflow-wrap: anywhere; }
.v5-preview__evidence li > small { display: block; margin-top: 8px; color: var(--td-warning-color-8); font-family: ui-monospace, monospace; overflow-wrap: anywhere; }
.v5-preview__empty { margin: 0; color: var(--td-text-color-placeholder); }
.v5-preview__empty-workspace { display: grid; flex: 1; min-height: 0; place-items: center; overflow: auto; padding: 30px; color: var(--td-text-color-secondary); }
.v5-preview__schema-grid { display: grid; grid-template-columns: repeat(4, minmax(130px, 1fr)); width: min(760px, 100%); border-top: 1px solid var(--td-component-border); border-left: 1px solid var(--td-component-border); }
.v5-preview__schema-grid button { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 58px; padding: 10px 12px; border: 0; border-right: 1px solid var(--td-component-border); border-bottom: 1px solid var(--td-component-border); background: transparent; color: var(--td-text-color-primary); text-align: left; cursor: pointer; }
.v5-preview__schema-grid button.active { background: var(--td-brand-color-light); color: var(--td-brand-color); }
.v5-preview__schema-grid strong { color: var(--td-text-color-placeholder); font-size: 18px; }
@media (max-width: 1100px) {
  .v5-preview__form { grid-template-columns: repeat(3, minmax(140px, 1fr)); }
  .v5-preview__browser { grid-template-columns: 270px minmax(0, 1fr); }
}
@media (max-width: 760px) {
  .v5-preview__toolbar { grid-template-columns: minmax(0, 1fr) 36px auto; }
  .v5-preview__mode { grid-column: 1 / -1; grid-row: 2; }
  .v5-preview__form { grid-template-columns: 1fr 1fr; max-height: 250px; overflow: auto; }
  .v5-preview__browser { grid-template-columns: 1fr; }
  .v5-preview__navigation { max-height: 42vh; border-right: 0; border-bottom: 1px solid var(--td-component-border); }
  .v5-preview__metadata { grid-template-columns: 1fr; }
  .v5-preview__metadata div:nth-child(odd) { padding-right: 0; }
  .v5-preview__schema-grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
}
</style>
