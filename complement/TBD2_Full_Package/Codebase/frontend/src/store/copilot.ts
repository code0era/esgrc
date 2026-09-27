import { create } from 'zustand'

export interface Message {
  id:        string
  role:      'user' | 'assistant'
  content:   string
  createdAt: string
  error?:    boolean
}

// Shown in place of an empty assistant bubble when the stream ends without
// ever producing a token - e.g. the SSE connection drops, or the server
// itself emits a `type: 'error'` event. Without this, finalizeAssistant just
// flips isStreaming back to false and the bubble is left showing "Thinking..."
// forever with no signal that anything went wrong.
const STREAM_ERROR_TEXT = 'Sorry, something went wrong while generating a response. Please try again.'

interface CopilotState {
  isOpen:       boolean
  messages:     Message[]
  isStreaming:  boolean
  streamRunId:  string | null
  sessionId:    string | null

  open:          () => void
  close:         () => void
  toggle:        () => void
  addUserMessage:    (content: string) => string   // returns msg id
  startAssistant:    (runId: string) => string      // returns placeholder id
  appendToken:       (msgId: string, token: string) => void
  finalizeAssistant: (msgId: string, error?: boolean) => void
  addErrorMessage:   (content?: string) => string   // returns msg id
  clearHistory:      () => void
  setSessionId:      (id: string) => void
}

let _msgCounter = 0
const nextId = () => `msg-${Date.now()}-${++_msgCounter}`

export const useCopilotStore = create<CopilotState>()((set, get) => ({
  isOpen:      false,
  messages:    [],
  isStreaming: false,
  streamRunId: null,
  sessionId:   null,

  open:   () => set({ isOpen: true }),
  close:  () => set({ isOpen: false }),
  toggle: () => set((s) => ({ isOpen: !s.isOpen })),

  addUserMessage: (content) => {
    const id = nextId()
    set((s) => ({
      messages: [...s.messages, {
        id, role: 'user', content, createdAt: new Date().toISOString(),
      }],
    }))
    return id
  },

  startAssistant: (runId) => {
    const id = nextId()
    set((s) => ({
      isStreaming: true,
      streamRunId: runId,
      messages: [...s.messages, {
        id, role: 'assistant', content: '', createdAt: new Date().toISOString(),
      }],
    }))
    return id
  },

  appendToken: (msgId, token) => set((s) => ({
    messages: s.messages.map((m) =>
      m.id === msgId ? { ...m, content: m.content + token } : m
    ),
  })),

  finalizeAssistant: (msgId, error) => set((s) => ({
    isStreaming: false,
    streamRunId: null,
    messages: error
      ? s.messages.map((m) =>
          m.id === msgId
            ? { ...m, error: true, content: m.content || STREAM_ERROR_TEXT }
            : m
        )
      : s.messages,
  })),

  // Used when the initial POST /copilot/message never makes it far enough to
  // get a run_id - no stream ever starts, so finalizeAssistant (which expects
  // an in-flight streamRunId to clear) doesn't fit. Without this, a failed
  // send left the user's message sitting with no reply and no indication
  // anything went wrong.
  addErrorMessage: (content = STREAM_ERROR_TEXT) => {
    const id = nextId()
    set((s) => ({
      messages: [...s.messages, {
        id, role: 'assistant', content, createdAt: new Date().toISOString(), error: true,
      }],
    }))
    return id
  },

  // Also drops any in-flight stream: the assistant message it was targeting no
  // longer exists once messages is wiped, so isStreaming/streamRunId left set
  // would permanently disable the composer with nothing left to clear them.
  clearHistory: () => set({ messages: [], sessionId: null, isStreaming: false, streamRunId: null }),

  setSessionId: (id) => set({ sessionId: id }),
}))
