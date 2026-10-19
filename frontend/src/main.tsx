import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import 'maplibre-gl/dist/maplibre-gl.css'
import './styles.css'
import { App } from './App'
import { ForecastPage } from './ForecastPage'
// This entry module renders directly; the page stays split from the map bundle.
// eslint-disable-next-line react-refresh/only-export-components
const AstronomyPage = lazy(() =>
  import('./AstronomyPage').then((module) => ({
    default: module.AstronomyPage,
  })),
)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) =>
        failureCount < 2 &&
        !(error instanceof Error && error.message.includes('(404)')),
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {window.location.pathname.replace(/\/$/, '') === '/astronomy' ? (
        <Suspense fallback={<p>Opening Astronomy…</p>}>
          <AstronomyPage />
        </Suspense>
      ) : window.location.pathname.replace(/\/$/, '') === '/forecast' ? (
        <ForecastPage />
      ) : (
        <App />
      )}
    </QueryClientProvider>
  </StrictMode>,
)
