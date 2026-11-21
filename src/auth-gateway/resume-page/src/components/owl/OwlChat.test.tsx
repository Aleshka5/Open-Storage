import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MAX_QUESTION_LENGTH } from '../../chat'
import { mockFetch } from '../../test/fixtures'
import { OwlChat } from './OwlChat'

function sse(...frames: string[]): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder()
      for (const f of frames) controller.enqueue(encoder.encode(f))
      controller.close()
    },
  })
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

/** The answer may hold links into the tree, so the panel needs a router. */
function renderChat(onClose: () => void = () => {}) {
  return render(
    <MemoryRouter>
      <OwlChat onClose={onClose} />
    </MemoryRouter>,
  )
}

describe('OwlChat', () => {
  it('asks with the placeholder field and streams the answer', async () => {
    mockFetch(() => sse('data: {"delta":"He builds "}\n\n', 'data: {"delta":"agents."}\n\n', 'data: [DONE]\n\n'))
    renderChat()

    const input = screen.getByPlaceholderText('Ask me something')
    await userEvent.type(input, 'What does he do?')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByText('He builds agents.')).toBeInTheDocument()
    expect(screen.getByText('What does he do?')).toBeInTheDocument()
  })

  it('keeps no history: a second question replaces the first', async () => {
    let answer = 'first answer'
    const fetchMock = mockFetch(() => sse(`data: {"delta":"${answer}"}\n\n`, 'data: [DONE]\n\n'))
    renderChat()

    const input = screen.getByPlaceholderText('Ask me something')
    await userEvent.type(input, 'one')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('first answer')).toBeInTheDocument()

    answer = 'second answer'
    await userEvent.type(input, 'two')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('second answer')).toBeInTheDocument()

    expect(screen.queryByText('first answer')).not.toBeInTheDocument()
    // Every request carries this question only — no prior turns.
    for (const call of fetchMock.mock.calls) {
      const body = JSON.parse(String((call[1] as RequestInit).body))
      expect(Object.keys(body)).toEqual(['question'])
    }
  })

  it('sends the question to the gateway route, with no credential of its own', async () => {
    const fetchMock = mockFetch(() => sse('data: {"delta":"ok"}\n\n', 'data: [DONE]\n\n'))
    renderChat()

    await userEvent.type(screen.getByPlaceholderText('Ask me something'), 'hi')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    await screen.findByText('ok')

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/chat')
    expect(init.method).toBe('POST')
    // The gateway holds the upstream key; the page must never carry one.
    const headers = new Headers(init.headers)
    expect(headers.get('Authorization')).toBeNull()
    expect(headers.get('X-Api-Key')).toBeNull()
    expect(headers.get('X-Chat-Session')).toBeTruthy()
  })

  it('caps the question at 255 characters', () => {
    renderChat()
    const input = screen.getByPlaceholderText('Ask me something')
    expect(input).toHaveAttribute('maxLength', String(MAX_QUESTION_LENGTH))
  })

  it('shows the error instead of an answer when the owl cannot reach its brain', async () => {
    mockFetch(() => new Response(JSON.stringify({ error: 'chat is not configured' }), { status: 503 }))
    renderChat()

    await userEvent.type(screen.getByPlaceholderText('Ask me something'), 'hi')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('chat is not configured')
  })

  it('surfaces a failure that arrives inside the stream', async () => {
    mockFetch(() => sse('data: {"error":"The owl could not reach its brain."}\n\n'))
    renderChat()

    await userEvent.type(screen.getByPlaceholderText('Ask me something'), 'hi')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('could not reach its brain')
  })

  it('closes on Escape and on the close button', async () => {
    const onClose = vi.fn()
    renderChat(onClose)

    await userEvent.click(screen.getByRole('button', { name: 'Close chat' }))
    expect(onClose).toHaveBeenCalledTimes(1)

    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('turns a page path in the answer into a link into the tree', async () => {
    mockFetch(() =>
      sse('data: {"delta":"The numbers are on /achieve"}\n\n', 'data: {"delta":"ments/numbers."}\n\n', 'data: [DONE]\n\n'),
    )
    renderChat()

    await userEvent.type(screen.getByPlaceholderText('Ask me something'), 'numbers?')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    // The path arrived split across two deltas and still resolves.
    const link = await screen.findByRole('link', { name: '/achievements/numbers' })
    expect(link).toHaveAttribute('href', '/achievements/numbers')
  })
})
