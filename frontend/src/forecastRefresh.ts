import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

const FORECAST_QUERIES = [
  'forecast-regions',
  'forecast-hourly',
  'forecast-official-hourly',
  'forecast-precipitation',
  'forecast-current',
]

// Resume events are coordinated here, including browser back/forward restoration.
export const forecastRefreshOptions = {
  staleTime: 300_000,
  refetchInterval: 300_000,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
}

export function useForecastRefresh() {
  const queryClient = useQueryClient()
  const [now, setNow] = useState(() => new Date())
  const [online, setOnline] = useState(() => navigator.onLine)
  const lastResume = useRef(0)
  const refresh = useCallback(() => {
    setNow(new Date())
    for (const key of FORECAST_QUERIES) {
      // A focus/visibility/online burst must not cancel an update already underway.
      void queryClient.invalidateQueries(
        { queryKey: [key] },
        { cancelRefetch: false },
      )
    }
  }, [queryClient])

  useEffect(() => {
    const resume = () => {
      setOnline(navigator.onLine)
      if (document.visibilityState === 'hidden') return
      setNow(new Date())
      if (Date.now() - lastResume.current < 1000) return
      lastResume.current = Date.now()
      refresh()
    }
    const offline = () => setOnline(false)
    const timer = window.setInterval(() => setNow(new Date()), 60_000)
    document.addEventListener('visibilitychange', resume)
    window.addEventListener('focus', resume)
    window.addEventListener('pageshow', resume)
    window.addEventListener('online', resume)
    window.addEventListener('offline', offline)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', resume)
      window.removeEventListener('focus', resume)
      window.removeEventListener('pageshow', resume)
      window.removeEventListener('online', resume)
      window.removeEventListener('offline', offline)
    }
  }, [refresh])
  return { now, refresh, online }
}
