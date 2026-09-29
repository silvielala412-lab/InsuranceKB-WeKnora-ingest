import {
  parseV5CandidatePreview,
  type V5CandidatePreview,
} from './v5/v5PreviewContract.ts'
import {
  parseV5ProviderTrialRun,
  type V5ProviderTrialRun,
} from './v5/v5ProviderTrialContract.ts'
import {
  parseV5DynamicFieldGapfillResponse,
  type V5DynamicFieldGapfillRequest,
  type V5DynamicFieldGapfillResponse,
} from './v5/v5DynamicGapfillContract.ts'
import {
  parseV5SearchResult,
  type V5SearchResult,
} from './v5/v5SearchContract.ts'

export interface V5SearchStreamMeta {
  readonly query: string
  readonly provider: 'local' | 'bailian'
  readonly model: string | null
  readonly matches: V5SearchResult['matches']
  readonly provider_error: string | null
}

export interface V5SearchStreamHandlers {
  readonly onMeta?: (meta: V5SearchStreamMeta) => void
  readonly onDelta: (content: string) => void
  readonly onDone?: (result: Pick<V5SearchResult, 'provider' | 'model' | 'provider_error'>) => void
}

export interface V5CatalogSchemaIndex {
  readonly ordinal: number
  readonly insurance_class: string
  readonly schema_id: string
  readonly field_count: number
}

export interface V5CatalogIndex {
  readonly catalog_id: 'insurance-product-schema-v5'
  readonly catalog_sha256: string
  readonly source_sha256: string
  readonly schemas: readonly V5CatalogSchemaIndex[]
}

export interface V5PreviewRequest {
  readonly source_revision_id: string
  readonly catalog_id: 'insurance-product-schema-v5'
  readonly schema_id: string
  readonly product_id: string
  readonly product_version_id: string
  readonly product_display_name: string
  readonly reviewed_insurance_class: string
  readonly classification: null
  readonly source_text: string
}

export interface V5PreviewClient {
  getCatalog(): Promise<V5CatalogIndex>
  getProviderRun(): Promise<V5ProviderTrialRun | null>
  createPreview(mode: 'fixture' | 'llm', request: V5PreviewRequest): Promise<V5CandidatePreview>
  runDynamicFieldGapfill(
    request: V5DynamicFieldGapfillRequest,
  ): Promise<V5DynamicFieldGapfillResponse>
  search?(query: string, limit?: number): Promise<V5SearchResult>
  searchStream?(
    query: string,
    handlers: V5SearchStreamHandlers,
    limit?: number,
    signal?: AbortSignal,
  ): Promise<void>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function invalidCatalog(): never {
  throw new Error('V5_CATALOG_RESPONSE_INVALID')
}

function parseCatalog(value: unknown): V5CatalogIndex {
  if (
    !isRecord(value)
    || value.contract !== 'insurance-v5-schema-catalog.v1'
    || value.catalog_id !== 'insurance-product-schema-v5'
    || typeof value.catalog_sha256 !== 'string'
    || !/^[a-f0-9]{64}$/.test(value.catalog_sha256)
    || typeof value.source_sha256 !== 'string'
    || !/^[a-f0-9]{64}$/.test(value.source_sha256)
    || !Array.isArray(value.schemas)
    || value.schemas.length !== 11
  ) invalidCatalog()

  const schemas = value.schemas.map((schema, ordinal) => {
    if (
      !isRecord(schema)
      || schema.ordinal !== ordinal
      || typeof schema.insurance_class !== 'string'
      || !schema.insurance_class
      || schema.schema_id !== `insurance-product-schema-v5:${schema.insurance_class}`
      || !Array.isArray(schema.fields)
      || schema.fields.length < 1
    ) invalidCatalog()
    return Object.freeze({
      ordinal,
      insurance_class: schema.insurance_class,
      schema_id: schema.schema_id as string,
      field_count: schema.fields.length,
    })
  })
  if (new Set(schemas.map(schema => schema.insurance_class)).size !== schemas.length) invalidCatalog()
  return Object.freeze({
    catalog_id: 'insurance-product-schema-v5',
    catalog_sha256: value.catalog_sha256,
    source_sha256: value.source_sha256,
    schemas: Object.freeze(schemas),
  })
}

async function responseJson(response: Response): Promise<unknown> {
  const value: unknown = await response.json()
  if (!response.ok) {
    const detail = isRecord(value) && typeof value.detail === 'string'
      ? value.detail
      : `HTTP_${response.status}`
    throw new Error(detail)
  }
  return value
}

export function createV5PreviewClient(fetcher: typeof fetch = fetch): V5PreviewClient {
  return Object.freeze({
    async getCatalog(): Promise<V5CatalogIndex> {
      const response = await fetcher('/v5-preview-api/catalog', { method: 'GET' })
      return parseCatalog(await responseJson(response))
    },
    async getProviderRun(): Promise<V5ProviderTrialRun | null> {
      const response = await fetcher('/v5-preview-api/provider-run', { method: 'GET' })
      const value: unknown = await response.json()
      if (response.status === 404 && isRecord(value)
        && value.detail === 'V5_PROVIDER_RUN_NOT_CONFIGURED') return null
      if (!response.ok) {
        const detail = isRecord(value) && typeof value.detail === 'string'
          ? value.detail
          : `HTTP_${response.status}`
        throw new Error(detail)
      }
      return parseV5ProviderTrialRun(value)
    },
    async createPreview(
      mode: 'fixture' | 'llm',
      request: V5PreviewRequest,
    ): Promise<V5CandidatePreview> {
      const path = mode === 'fixture'
        ? '/v5-preview-api/fixture-preview'
        : '/v5-preview-api/preview'
      const response = await fetcher(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      })
      return parseV5CandidatePreview(await responseJson(response))
    },
    async runDynamicFieldGapfill(
      request: V5DynamicFieldGapfillRequest,
    ): Promise<V5DynamicFieldGapfillResponse> {
      const response = await fetcher('/v5-preview-api/dynamic-field-gapfill', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      })
      return parseV5DynamicFieldGapfillResponse(await responseJson(response))
    },
    async search(query: string, limit = 20): Promise<V5SearchResult> {
      const response = await fetcher('/v5-preview-api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, limit }),
      })
      return parseV5SearchResult(await responseJson(response))
    },
    async searchStream(
      query: string,
      handlers: V5SearchStreamHandlers,
      limit = 20,
      signal?: AbortSignal,
    ): Promise<void> {
      const response = await fetcher('/v5-preview-api/search/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ query, limit }),
        signal,
      })
      if (!response.ok) {
        const detail = await response.text().catch(() => '')
        throw new Error(detail || `HTTP_${response.status}`)
      }
      if (!response.body) throw new Error('V5_SEARCH_STREAM_BODY_MISSING')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const consume = (raw: string) => {
        const payload = raw
          .split(/\r?\n/)
          .filter(line => line.startsWith('data:'))
          .map(line => line.slice(5).trim())
          .join('')
        if (!payload) return
        const event = JSON.parse(payload) as Record<string, unknown>
        if (event.type === 'meta') {
          handlers.onMeta?.({
            query: String(event.query || query),
            provider: event.provider === 'bailian' ? 'bailian' : 'local',
            model: typeof event.model === 'string' ? event.model : null,
            matches: Array.isArray(event.matches)
              ? parseV5SearchResult({
                contract: 'insurance-v5-search-response.v1',
                query: String(event.query || query),
                provider: event.provider === 'bailian' ? 'bailian' : 'local',
                model: typeof event.model === 'string' ? event.model : null,
                answer: 'streaming',
                matches: event.matches,
                provider_error: typeof event.provider_error === 'string' ? event.provider_error : null,
              }).matches
              : [],
            provider_error: typeof event.provider_error === 'string' ? event.provider_error : null,
          })
        } else if (event.type === 'delta' && typeof event.content === 'string') {
          handlers.onDelta(event.content)
        } else if (event.type === 'done') {
          handlers.onDone?.({
            provider: event.provider === 'bailian' ? 'bailian' : 'local',
            model: typeof event.model === 'string' ? event.model : null,
            provider_error: typeof event.provider_error === 'string' ? event.provider_error : null,
          })
        } else if (event.type === 'error') {
          throw new Error(typeof event.detail === 'string' ? event.detail : 'V5_SEARCH_STREAM_FAILED')
        }
      }
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split(/\r?\n\r?\n/)
        buffer = events.pop() || ''
        events.forEach(consume)
      }
      buffer += decoder.decode()
      if (buffer.trim()) consume(buffer)
    },
  })
}
