import { describe, expect, it } from 'vitest'
import { parseProgressData, SseParser } from './sse'

const progress = (id: number) =>
  `id: ${id}\r\nevent: progress\r\ndata: {"id": ${id}, "type": "status", "message": "Planning the analysis", "payload": {"phase": "planning"}, "created_at": "2026-10-12T12:50:00Z"}\r\n\r\n`

describe('SseParser', () => {
  it('parses complete CRLF messages', () => {
    const parser = new SseParser()
    const messages = parser.push(progress(1) + progress(2))
    expect(messages).toHaveLength(2)
    expect(messages[0]).toMatchObject({ event: 'progress', id: '1' })
    expect(parseProgressData(messages[1].data)?.id).toBe(2)
  })

  it('handles messages split across arbitrary chunks, including inside CRLF', () => {
    const parser = new SseParser()
    const text = progress(7) + 'event: end\r\ndata: {"status": "completed"}\r\n\r\n'
    const out = []
    for (let i = 0; i < text.length; i += 3) out.push(...parser.push(text.slice(i, i + 3)))
    expect(out.map((m) => m.event)).toEqual(['progress', 'end'])
    expect(JSON.parse(out[1].data)).toEqual({ status: 'completed' })
  })

  it('splits exactly between CR and LF without emitting a phantom message', () => {
    const parser = new SseParser()
    expect(parser.push('event: progress\r\ndata: {"a":1}\r')).toEqual([])
    expect(parser.push('\ndata: {"b":2}\r\n\r\n')).toEqual([
      { event: 'progress', data: '{"a":1}\n{"b":2}', id: undefined },
    ])
  })

  it('ignores comments (keep-alive pings) and defaults the event name', () => {
    const parser = new SseParser()
    const out = parser.push(': ping - 2026-10-12\n\ndata: hello\n\n')
    expect(out).toEqual([{ event: 'message', data: 'hello', id: undefined }])
  })

  it('supports LF-only streams', () => {
    const parser = new SseParser()
    expect(parser.push('event: end\ndata: {}\n\n')).toHaveLength(1)
  })
})

describe('parseProgressData', () => {
  it('returns a typed event', () => {
    const e = parseProgressData(
      '{"id": 3, "type": "step_started", "message": "Aggregate", "payload": {"tool": "sql"}, "created_at": "x"}',
    )
    expect(e).toEqual({ id: 3, type: 'step_started', message: 'Aggregate', payload: { tool: 'sql' }, created_at: 'x' })
  })
  it('rejects malformed data', () => {
    expect(parseProgressData('not json')).toBeNull()
    expect(parseProgressData('{"type": "status"}')).toBeNull()
  })
})
