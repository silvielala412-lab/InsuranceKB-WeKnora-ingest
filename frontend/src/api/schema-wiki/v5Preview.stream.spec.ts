import { describe, expect, it } from 'vitest'

import { createV5PreviewClient } from './v5Preview.ts'

describe('V5 preview search stream client', () => {
  it('parses metadata, answer deltas, and completion events', async () => {
    const source = [
      `data: ${JSON.stringify({
        type: 'meta',
        query: '等待期',
        provider: 'bailian',
        model: 'qwen-plus',
        matches: [],
        provider_error: null,
      })}\n\n`,
      `data: ${JSON.stringify({ type: 'delta', content: '等待期为30天。' })}\n\n`,
      `data: ${JSON.stringify({
        type: 'done',
        provider: 'bailian',
        model: 'qwen-plus',
        provider_error: null,
      })}\n\n`,
    ].join('')
    const client = createV5PreviewClient(async () => new Response(source, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    }))
    const events: string[] = []
    let provider = ''

    await client.searchStream?.('等待期', {
      onMeta: meta => {
        events.push(`meta:${meta.query}`)
        provider = meta.provider
      },
      onDelta: content => events.push(`delta:${content}`),
      onDone: result => events.push(`done:${result.model}`),
    })

    expect(events).toEqual(['meta:等待期', 'delta:等待期为30天。', 'done:qwen-plus'])
    expect(provider).toBe('bailian')
  })
})
