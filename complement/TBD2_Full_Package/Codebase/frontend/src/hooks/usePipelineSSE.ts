import { useEffect, useRef, useCallback } from 'react'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { usePipelineStore, SSEStepEvent, RunStatus } from '@/store/pipeline'
import { useAuthStore } from '@/store/auth'
import { refreshAccessToken } from '@/lib/axios'

const MAX_RETRIES  = 5
const RETRY_DELAY  = 3_000   // ms

class FatalSSEError extends Error {}

/** Thrown from onopen after a successful refresh-and-reconnect, so the
 * current (stale-token) fetchEventSource call stops without being treated
 * as a real failure - the new connect() call it triggered takes over. */
class ReauthenticatedError extends Error {}

/**
 * Connects to the SSE stream for a pipeline run and dispatches
 * step events to pipelineStore. Reconnects up to 5 times on error.
 * Closes automatically when run reaches a terminal state.
 *
 * Uses fetch (not native EventSource) so the JWT travels as a normal
 * Authorization header instead of a URL query param - EventSource can't set
 * headers, and a query-param token lands in server/proxy access logs.
 */
export function usePipelineSSE(runId: string | null) {
  const applySSEEvent  = usePipelineStore((s) => s.applySSEEvent)
  const setRunStatus   = usePipelineStore((s) => s.setRunStatus)
  const setSSEStatus   = usePipelineStore((s) => s.setSSEStatus)

  const abortRef       = useRef<AbortController | null>(null)
  const retriesRef     = useRef(0)
  // Access tokens live ~30min; a pipeline run can outlast that. Guards
  // against looping refresh<->401 forever if the refresh token itself is
  // also no longer valid - one refresh attempt per connect(), not per
  // process lifetime (a later, separate expiry should get its own attempt).
  const hasRetriedAuthRef = useRef(false)

  const close = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    setSSEStatus('closed')
  }, [setSSEStatus])

  const connect = useCallback(() => {
    if (!runId) return

    const controller = new AbortController()
    abortRef.current = controller
    setSSEStatus('connecting')

    // Read the token live (not from a hook-render closure) so a reconnect
    // triggered from within onopen below always sends the current token,
    // never one captured before a refresh.
    const token = useAuthStore.getState().token

    fetchEventSource(`/api/pipelines/runs/${runId}/stream`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal: controller.signal,
      openWhenHidden: true,

      async onopen(response) {
        if (response.status === 401 && !hasRetriedAuthRef.current) {
          // The access token (~30min lifetime) aged out mid-run. Unlike the
          // axios `api` instance, this hook connects via `fetch` directly,
          // so it never goes through axios's own refresh-on-401 interceptor
          // and previously treated this as fatal - a long-running pipeline
          // silently stopped getting live updates until the page was
          // reloaded. Exchange the refresh token (sharing axios.ts's queue,
          // so this can't race a concurrent axios-triggered refresh) and
          // reconnect once with the new token.
          hasRetriedAuthRef.current = true
          try {
            await refreshAccessToken()
            connect()
          } catch {
            // refreshAccessToken() already logged out on failure.
          }
          throw new ReauthenticatedError('refreshed - handing off to a new connect()')
        }
        if (!response.ok) throw new FatalSSEError(`SSE handshake failed: ${response.status}`)
        hasRetriedAuthRef.current = false
        retriesRef.current = 0
        setSSEStatus('connected')
      },

      onmessage(e) {
        try {
          const data = JSON.parse(e.data)

          // Terminal run events
          if (data.event === 'run_completed') {
            setRunStatus('COMPLETED' as RunStatus, 100)
            close()
            return
          }
          if (data.event === 'run_failed') {
            setRunStatus('FAILED' as RunStatus)
            close()
            return
          }
          if (data.event === 'run_cancelled') {
            setRunStatus('CANCELLED' as RunStatus)
            close()
            return
          }

          // Step events
          if (data.event?.startsWith('step_')) {
            applySSEEvent(data as SSEStepEvent)
            if (data.status === 'RUNNING') {
              setRunStatus('RUNNING' as RunStatus, data.pct)
            }
          }
        } catch {
          // ignore parse errors
        }
      },

      onerror(err) {
        if (err instanceof ReauthenticatedError) {
          // Not a real error - connect() has already been called again with
          // a fresh token. Stop this instance quietly, leave sseStatus as
          // whatever the new connect() just set it to ('connecting').
          throw err
        }
        setSSEStatus('error')
        if (err instanceof FatalSSEError || retriesRef.current >= MAX_RETRIES) {
          setSSEStatus('closed')
          throw err ?? new FatalSSEError('max retries exceeded')  // throwing stops the library's own retry loop
        }
        retriesRef.current += 1
        return RETRY_DELAY  // returning a number tells the library to retry after this delay
      },
    }).catch(() => {
      // FatalSSEError / ReauthenticatedError / abort - already handled above
    })
  }, [runId, applySSEEvent, setRunStatus, setSSEStatus, close])

  useEffect(() => {
    if (!runId) return
    connect()
    return close
  }, [runId, connect, close])

  return {
    connectionStatus: usePipelineStore((s) => s.sseStatus),
  }
}
