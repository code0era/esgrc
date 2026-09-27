import { describe, it, expect, beforeEach } from 'vitest'
import { useCopilotStore } from './copilot'

beforeEach(() => {
  useCopilotStore.setState({
    isOpen: false, messages: [], isStreaming: false, streamRunId: null, sessionId: null,
  })
})

describe('clearHistory', () => {
  it('resets streaming state along with messages', () => {
    // Mid-stream: a real assistant reply is in flight when the user clicks
    // Clear history. Without resetting isStreaming/streamRunId here, nothing
    // left in the app can ever flip isStreaming back to false - the composer
    // stays disabled until a full page reload.
    useCopilotStore.getState().addUserMessage('What are the top risks?')
    useCopilotStore.getState().startAssistant('run-123')
    expect(useCopilotStore.getState().isStreaming).toBe(true)

    useCopilotStore.getState().clearHistory()

    const s = useCopilotStore.getState()
    expect(s.messages).toEqual([])
    expect(s.sessionId).toBeNull()
    expect(s.isStreaming).toBe(false)
    expect(s.streamRunId).toBeNull()
  })

  it('is a no-op on streaming state when nothing was in flight', () => {
    useCopilotStore.getState().addUserMessage('hello')
    useCopilotStore.getState().clearHistory()

    const s = useCopilotStore.getState()
    expect(s.messages).toEqual([])
    expect(s.isStreaming).toBe(false)
  })
})

describe('finalizeAssistant', () => {
  it('leaves a completed message untouched when finalized without an error', () => {
    useCopilotStore.getState().addUserMessage('What are the top risks?')
    const msgId = useCopilotStore.getState().startAssistant('run-123')
    useCopilotStore.getState().appendToken(msgId, 'Here are the risks...')

    useCopilotStore.getState().finalizeAssistant(msgId)

    const s = useCopilotStore.getState()
    expect(s.isStreaming).toBe(false)
    expect(s.streamRunId).toBeNull()
    const msg = s.messages.find((m) => m.id === msgId)
    expect(msg?.content).toBe('Here are the risks...')
    expect(msg?.error).toBeUndefined()
  })

  it('marks the message as errored and fills in fallback text when the stream failed before any tokens arrived', () => {
    // SSE error events (or a dropped connection) used to leave the bubble
    // stuck on "Thinking..." forever with nothing telling the user the
    // response failed - a silent failure. finalizeAssistant(id, true) is how
    // useCopilotSSE now signals that case.
    useCopilotStore.getState().addUserMessage('What are the top risks?')
    const msgId = useCopilotStore.getState().startAssistant('run-123')

    useCopilotStore.getState().finalizeAssistant(msgId, true)

    const s = useCopilotStore.getState()
    expect(s.isStreaming).toBe(false)
    const msg = s.messages.find((m) => m.id === msgId)
    expect(msg?.error).toBe(true)
    expect(msg?.content).not.toBe('')
  })

  it('marks the message as errored but preserves any partial text already streamed', () => {
    useCopilotStore.getState().addUserMessage('What are the top risks?')
    const msgId = useCopilotStore.getState().startAssistant('run-123')
    useCopilotStore.getState().appendToken(msgId, 'Partial answer before it broke')

    useCopilotStore.getState().finalizeAssistant(msgId, true)

    const msg = useCopilotStore.getState().messages.find((m) => m.id === msgId)
    expect(msg?.error).toBe(true)
    expect(msg?.content).toBe('Partial answer before it broke')
  })
})

describe('addErrorMessage', () => {
  it('appends an errored assistant message without touching streaming state', () => {
    // Covers the initial POST /copilot/message failing outright - before a
    // run_id (and therefore a stream) ever exists. Unlike finalizeAssistant,
    // there is no in-flight isStreaming/streamRunId to clear here.
    useCopilotStore.getState().addUserMessage('What are the top risks?')

    const msgId = useCopilotStore.getState().addErrorMessage()

    const s = useCopilotStore.getState()
    expect(s.isStreaming).toBe(false)
    expect(s.streamRunId).toBeNull()
    const msg = s.messages.find((m) => m.id === msgId)
    expect(msg?.role).toBe('assistant')
    expect(msg?.error).toBe(true)
    expect(msg?.content).toBeTruthy()
  })

  it('accepts a custom message', () => {
    const msgId = useCopilotStore.getState().addErrorMessage('Network unreachable')
    const msg = useCopilotStore.getState().messages.find((m) => m.id === msgId)
    expect(msg?.content).toBe('Network unreachable')
    expect(msg?.error).toBe(true)
  })
})
