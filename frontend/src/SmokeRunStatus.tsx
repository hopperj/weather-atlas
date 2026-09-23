import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { SmokeRunDetails } from './SmokeRunDetails'
import { smokeApi } from './smokeApi'
import type { SmokeRun } from './smokeSchemas'

const terminalStates = new Set([
  'complete',
  'complete_with_warnings',
  'failed',
  'cancelled',
])

const stateLabels: Record<string, string> = {
  queued: 'Queued',
  resolving_inputs: 'Resolving inputs',
  emissions_running: 'Estimating emissions',
  transport_running: 'Transporting smoke',
  processing_outputs: 'Preparing map layers',
  publishing: 'Publishing map layers',
  complete: 'Complete',
  complete_with_warnings: 'Complete with warnings',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

export function SmokeRunStatus({
  runId,
  onClose,
  onPublished,
}: {
  runId: string
  onClose: () => void
  onPublished: (run: SmokeRun) => void
}) {
  const queryClient = useQueryClient()
  const runQuery = useQuery({
    queryKey: ['smoke-run', runId],
    queryFn: ({ signal }) => smokeApi.getRun(runId, signal),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (!status || !terminalStates.has(status)) return 4_000
      return false
    },
  })
  const cancel = useMutation({
    mutationFn: () => smokeApi.cancelRun(runId),
    onSuccess: (run) => queryClient.setQueryData(['smoke-run', runId], run),
  })
  const run = runQuery.data
  const published =
    run?.status === 'complete' || run?.status === 'complete_with_warnings'

  return (
    <section className="smoke-run-status" aria-live="polite">
      <div className="smoke-status-heading">
        <div>
          <p className="eyebrow">SMOKE SIMULATION</p>
          <strong>
            {run ? (stateLabels[run.status] ?? run.status) : 'Loading run'}
          </strong>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close smoke run status"
        >
          ×
        </button>
      </div>
      {runQuery.error && (
        <p className="smoke-error">{runQuery.error.message}</p>
      )}
      {run && (
        <>
          <div className={`smoke-progress state-${run.status}`}>
            <span />
          </div>
          <SmokeRunDetails run={run} />
          {run.errorMessage && (
            <p className="smoke-error">{run.errorMessage}</p>
          )}
          {run.warnings.map((warning, index) => (
            <p className="smoke-warning" key={`${index}-${String(warning)}`}>
              {typeof warning === 'string' ? warning : JSON.stringify(warning)}
            </p>
          ))}
          <div className="smoke-status-actions">
            {!terminalStates.has(run.status) && (
              <button
                className="text-button danger"
                type="button"
                disabled={cancel.isPending}
                onClick={() => cancel.mutate()}
              >
                Request cancellation
              </button>
            )}
            {published && (
              <button
                className="text-button"
                type="button"
                onClick={() => onPublished(run)}
              >
                View results on map
              </button>
            )}
          </div>
        </>
      )}
    </section>
  )
}
