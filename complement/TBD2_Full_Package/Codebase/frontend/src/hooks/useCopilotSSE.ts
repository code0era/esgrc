import { useEffect, useRef, useCallback } from 'react'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { useCopilotStore } from '@/store/copilot'
import { useAuthStore } from '@/store/auth'
import { refreshAccessToken } from '@/lib/axios'

class FatalSSEError extends Error {}

/** Thrown from onopen after a successful refresh-and-reconnect, so the
 * current (stale-token) fetchEventSource call stops without being treated
 * as a real failure - the new connect() call it triggered takes over. */
class ReauthenticatedError extends Error {}

/**
 * Connects to the Co-Pilot SSE stream and appends tokens into
 * the copilotStore message identified by msgId.
 *
 * Uses fetch (not native EventSource) so the JWT travels as a normal
 * Authorization header instead of a URL query param - EventSource can't set
 * headers, and a query-param token lands in server/proxy access logs.
 */
export function useCopilotSSE(runId: string | null, msgId: string | null) {
  const appendToken       = useCopilotStore((s) => s.appendToken)
  const finalizeAssistant = useCopilotStore((s) => s.finalizeAssistant)
  const abortRef          = useRef<AbortController | null>(null)
  // One refresh-and-reconnect attempt per connect() - guards against looping
  // refresh<->401 forever if the refresh token itself is also no longer valid.
  const hasRetriedAuthRef = useRef(false)

  const connect = useCallback(() => {
    if (!runId || !msgId) return

    const controller = new AbortController()
    abortRef.current = controller

    // Read the token live (not from a hook-render closure) so a reconnect
    // triggered from within onopen below always sends the current token,
    // never one captured before a refresh.
    const token = useAuthStore.getState().token

    fetchEventSource(`/api/copilot/stream/${runId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal: controller.signal,
      openWhenHidden: true,

      async onopen(response) {
        if (response.status === 401 && !hasRetriedAuthRef.current) {
          // The access token aged out mid-stream. This hook connects via
          // `fetch` directly, so it never goes through axios's own
          // refresh-on-401 interceptor and previously treated this as
          // fatal - the composer would stay stuck disabled until reload.
          // Exchange the refresh token (sharing axios.ts's queue, so this
          // can't race a concurrent axios-triggered refresh) and reconnect
          // once with the new token.
          hasRetriedAuthRef.current = true
          try {
            await refreshAccessToken()
            connect()
          } catch {
            // refreshAccessToken() already logged out on failure.
            finalizeAssistant(msgId, true)
          }
          throw new ReauthenticatedError('refreshed - handing off to a new connect()')
        }
        if (!response.ok) throw new FatalSSEError(`SSE handshake failed: ${response.status}`)
        hasRetriedAuthRef.current = false
      },

      onmessage(e) {
        try {
          const data = JSON.parse(e.data)
          if (data.type === 'token' && data.text) {
            appendToken(msgId, data.text)
          }
          if (data.type === 'done' || data.type === 'error') {
            finalizeAssistant(msgId, data.type === 'error')
            controller.abort()
          }
        } catch {
          // ignore parse errors
        }
      },

      onerror(err) {
        if (err instanceof ReauthenticatedError) {
          // Not a real error - connect() has already been called again with
          // a fresh token. Stop this instance quietly.
          throw err
        }
        // No reconnect-with-retry here (matches prior EventSource behavior):
        // throwing stops the library's own retry loop after this one failure.
        finalizeAssistant(msgId, true)
        throw err instanceof FatalSSEError ? err : new FatalSSEError('stream error')
      },
    }).catch(() => {
      // FatalSSEError / ReauthenticatedError / abort - already handled above
    })
  }, [runId, msgId, appendToken, finalizeAssistant])

  useEffect(() => {
    if (!runId || !msgId) return
    connect()

    return () => {
      if (abortRef.current) {
        abortRef.current.abort()
        abortRef.current = null
      }
      // Whatever tore this effect down - unmount (panel closed), or runId/msgId
      // changing (clear history mid-stream) - the connection above is dead now.
      // finalizeAssistant is idempotent, so call it unconditionally: if 'done'/
      // 'error' already fired this is a no-op, and if nothing fired yet this is
      // the only place left that will ever clear isStreaming. Without it, the
      // composer stays disabled until a full page reload.
      finalizeAssistant(msgId)
    }
  }, [runId, msgId, connect, finalizeAssistant])
}
