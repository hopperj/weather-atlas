import type { SmokeRun } from './smokeSchemas'

function metric(run: SmokeRun, key: string) {
  const value = run.metrics[key]
  return typeof value === 'number' || typeof value === 'string' ? value : '—'
}

export function SmokeRunDetails({ run }: { run: SmokeRun }) {
  return (
    <div className="smoke-run-details">
      <div>
        <span>Run</span>
        <strong title={run.id}>{run.id.slice(0, 12)}</strong>
      </div>
      <div>
        <span>Fires</span>
        <strong>{metric(run, 'event_count')}</strong>
      </div>
      <div>
        <span>Map assets</span>
        <strong>{metric(run, 'asset_count')}</strong>
      </div>
      <div>
        <span>GFS cycle</span>
        <strong>
          {run.gfsCycleTime
            ? new Date(run.gfsCycleTime)
                .toISOString()
                .slice(0, 16)
                .replace('T', ' ')
            : 'Pending'}
        </strong>
      </div>
      <p>
        Primary wildfire emissions only · research estimate, not an official
        forecast.
      </p>
    </div>
  )
}
