import { useState, useRef, useEffect } from 'react'
import { X, Send, Trash2, Copy, Check, Bot, Sparkles } from 'lucide-react'
import { useCopilotStore } from '@/store/copilot'
import { useCopilotSSE } from '@/hooks/useCopilotSSE'
import api from '@/lib/axios'
import { cn } from '@/lib/utils'

function CopilotSSEBridge() {
  const streamRunId   = useCopilotStore((s) => s.streamRunId)
  const messages      = useCopilotStore((s) => s.messages)
  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant')
  useCopilotSSE(streamRunId, lastAssistant?.id ?? null)
  return null
}

function MessageBubble({ message }: { message: { id: string; role: string; content: string; createdAt: string; error?: boolean } }) {
  const [copied, setCopied] = useState(false)
  const isUser = message.role === 'user'

  const handleCopy = async () => {
    // Clipboard API can reject (denied permission, insecure context, the
    // document losing focus while this panel is open) - without a catch the
    // button silently does nothing on failure: no checkmark, no error, and
    // an unhandled promise rejection.
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (e) {
      console.error('Copy to clipboard failed', e)
    }
  }

  return (
    <div className={cn('flex gap-2 group', isUser ? 'flex-row-reverse' : 'flex-row')}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-accent-secondary/20 border border-accent-secondary/30
                        flex items-center justify-center flex-shrink-0 mt-1">
          <Bot size={14} className="text-accent-secondary" />
        </div>
      )}
      <div className={cn(
        'max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed relative',
        isUser
          ? 'bg-gradient-primary text-white rounded-tr-sm'
          : message.error
          ? 'bg-accent-danger/5 border border-accent-danger/30 text-accent-danger rounded-tl-sm'
          : 'bg-bg-elevated border border-border-subtle text-text-primary rounded-tl-sm'
      )}>
        {message.content || <span className="text-text-muted italic text-xs">Thinking...</span>}
        {!isUser && message.content && (
          <button
            className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-bg-surface border border-border-default
                       flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
            onClick={handleCopy}
            aria-label="Copy message"
          >
            {copied ? <Check size={10} className="text-accent-success" /> : <Copy size={10} className="text-text-muted" />}
          </button>
        )}
      </div>
    </div>
  )
}

export function CopilotPanel() {
  const close           = useCopilotStore((s) => s.close)
  const messages        = useCopilotStore((s) => s.messages)
  const isStreaming     = useCopilotStore((s) => s.isStreaming)
  const clearHistory    = useCopilotStore((s) => s.clearHistory)
  const addUserMessage  = useCopilotStore((s) => s.addUserMessage)
  const startAssistant  = useCopilotStore((s) => s.startAssistant)
  const addErrorMessage = useCopilotStore((s) => s.addErrorMessage)
  const setSessionId    = useCopilotStore((s) => s.setSessionId)
  const sessionId       = useCopilotStore((s) => s.sessionId)

  const [input, setInput]   = useState('')
  const bottomRef           = useRef<HTMLDivElement>(null)
  const inputRef            = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // This panel is hand-rolled (not Radix Dialog like FileUploadModal), so it
  // gets none of Dialog's built-in Escape-to-close behaviour for free.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [close])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || isStreaming) return
    setInput('')
    addUserMessage(text)

    try {
      const { data } = await api.post('/copilot/message', {
        message: text,
        session_id: sessionId ?? undefined,
      })
      if (data.session_id) setSessionId(data.session_id)
      startAssistant(data.run_id)
    } catch {
      // The request never got far enough to produce a run_id, so there's no
      // stream for useCopilotSSE to fail later - surface the failure here, or
      // the user's message sits with no reply and no sign anything went wrong.
      addErrorMessage()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <>
      <CopilotSSEBridge />
      <div
        className="fixed right-6 bottom-24 w-[400px] h-[600px] flex flex-col
                   bg-bg-surface border border-border-default rounded-2xl shadow-card-hover
                   animate-slide-up z-50 overflow-hidden"
        role="dialog"
        aria-label="AI Co-Pilot"
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border-subtle bg-bg-elevated">
          <div className="w-8 h-8 rounded-full bg-gradient-primary flex items-center justify-center">
            <Sparkles size={16} className="text-white" />
          </div>
          <div className="flex-1">
            <div className="font-semibold text-text-primary text-sm">AI Co-Pilot</div>
            <div className="text-[10px] text-text-muted">Risk Intelligence Assistant</div>
          </div>
          <button className="btn-icon" onClick={() => clearHistory()} aria-label="Clear history">
            <Trash2 size={15} />
          </button>
          <button className="btn-icon" onClick={close} aria-label="Close Co-Pilot">
            <X size={15} />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
              <div className="w-12 h-12 rounded-full bg-accent-secondary/10 flex items-center justify-center">
                <Bot size={24} className="text-accent-secondary" />
              </div>
              <div>
                <p className="text-sm font-medium text-text-primary">Ask me anything</p>
                <p className="text-xs text-text-muted mt-1">
                  Module performance, pipeline results,<br/>risk patterns, compliance status
                </p>
              </div>
              <div className="flex flex-wrap gap-2 justify-center mt-2">
                {[
                  'What are the top 3 risks?',
                  'Summarise the latest pipeline report',
                  'Which metrics are declining?',
                ].map((q) => (
                  <button
                    key={q}
                    className="text-xs px-3 py-1.5 rounded-full border border-accent-secondary/30
                               text-accent-secondary hover:bg-accent-secondary/10 transition-colors"
                    onClick={() => { setInput(q); inputRef.current?.focus() }}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) => <MessageBubble key={m.id} message={m} />)}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="px-4 py-3 border-t border-border-subtle">
          <div className="flex gap-2 items-end">
            <textarea
              ref={inputRef}
              id="copilot-input"
              className="flex-1 resize-none text-sm min-h-[40px] max-h-[120px] py-2.5"
              rows={1}
              placeholder="Ask about risks, pipeline results..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isStreaming}
              aria-label="Message to AI Co-Pilot"
            />
            <button
              className="btn-primary px-3 py-2.5 flex-shrink-0 self-end"
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              aria-label="Send message"
            >
              <Send size={16} />
            </button>
          </div>
          <div className="text-[10px] text-text-muted mt-1.5 text-center">
            Shift+Enter for newline · Enter to send
          </div>
        </div>
      </div>
    </>
  )
}
