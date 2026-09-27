import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { queryClient } from '@/lib/queryClient'
import './index.css'

async function enableMocking() {
  // Mocks (MSW) are on by default in dev, but can be turned off to talk to a
  // real backend by setting VITE_USE_MOCKS=false (see frontend/.env.local).
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS !== 'false') {
    const { worker } = await import('./mocks/browser')
    try {
      await worker.start({ onUnhandledRequest: 'bypass' })
    } catch (err) {
      // Service worker registration can fail in dev (blocked by browser
      // settings, non-localhost HTTP origin, storage disabled, etc). Without
      // this catch, the rejection propagates out of enableMocking(), the
      // .then() below never runs, and the app silently never renders - a
      // blank page with nothing but an "Uncaught (in promise)" line buried in
      // devtools to explain why.
      console.warn(
        '[MSW] Mock worker failed to start; continuing without request mocking.',
        err,
      )
    }
  }
}

enableMocking().then(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>,
  )
})
