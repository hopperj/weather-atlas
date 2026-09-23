import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { smokeApi } from './smokeApi'
import type { RunSubmission, SmokeScenarioConfigInput } from './smokeSchemas'

type Bbox = [number, number, number, number]
type Species = 'PM25' | 'CO' | 'BC'

const speciesOptions: Species[] = ['PM25', 'CO', 'BC']

function utcInput(value: string | null | undefined) {
  return value ? new Date(value).toISOString().slice(0, 16) : ''
}

function iso(value: string) {
  return new Date(`${value}:00Z`).toISOString()
}

export function SmokeRunBuilder({
  open,
  initialBbox,
  onClose,
  onSubmitted,
}: {
  open: boolean
  initialBbox: Bbox
  onClose: () => void
  onSubmitted: (submission: RunSubmission) => void
}) {
  const [step, setStep] = useState(0)
  const [name, setName] = useState('Map smoke scenario')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [bbox, setBbox] = useState<Bbox>(initialBbox)
  const [fireWeatherMode, setFireWeatherMode] = useState<
    'automatic_cwfis' | 'manual'
  >('automatic_cwfis')
  const [ffmc, setFfmc] = useState(92)
  const [dmc, setDmc] = useState(45)
  const [dc, setDc] = useState(320)
  const [species, setSpecies] = useState<Species[]>(speciesOptions)
  const [uncertainty, setUncertainty] = useState<'low' | 'central' | 'high'>(
    'central',
  )
  const [spacing, setSpacing] = useState<0.25 | 0.5 | 1>(0.5)
  const [particles, setParticles] = useState(250_000)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const capabilities = useQuery({
    queryKey: ['smoke-capabilities'],
    queryFn: ({ signal }) => smokeApi.capabilities(signal),
    enabled: open,
  })
  const sourceWindowStart = useMemo(() => {
    if (!start) return ''
    return new Date(new Date(iso(start)).getTime() - 24 * 3_600_000).toISOString()
  }, [start])
  const scenarioEnd = useMemo(() => (end ? iso(end) : ''), [end])
  const eventQuery = useQuery({
    queryKey: ['smoke-events', bbox, sourceWindowStart, scenarioEnd],
    queryFn: ({ signal }) =>
      smokeApi.listEvents(bbox, sourceWindowStart, scenarioEnd, signal),
    enabled: open && Boolean(sourceWindowStart && scenarioEnd),
  })

  useEffect(() => {
    if (!open) return
    setBbox(initialBbox)
    setStep(0)
    setError('')
  }, [initialBbox, open])

  useEffect(() => {
    if (!open || !capabilities.data) return
    setStart(utcInput(capabilities.data.availableStart))
    setEnd(utcInput(capabilities.data.availableEnd))
    setParticles(Math.min(250_000, capabilities.data.maximumParticles))
  }, [capabilities.data, open])

  const durationHours = useMemo(() => {
    if (!start || !end) return 0
    return (
      (new Date(iso(end)).getTime() - new Date(iso(start)).getTime()) /
      3_600_000
    )
  }, [end, start])
  const modelledEvents = useMemo(
    () =>
      (eventQuery.data?.items ?? []).filter(
        (event) =>
          event.model_eligible &&
          new Date(event.last_observed_at) < new Date(scenarioEnd) &&
          (fireWeatherMode === 'manual' || Boolean(event.fire_weather)),
      ),
    [eventQuery.data?.items, fireWeatherMode, scenarioEnd],
  )
  const minimumParticleBudget = useMemo(() => {
    if (!capabilities.data || durationHours <= 0) return 10_000
    const estimatedReleaseGroups =
      modelledEvents.length *
      Math.ceil(durationHours) *
      capabilities.data.maximumReleaseGroupsPerEventHour
    const required =
      estimatedReleaseGroups *
      capabilities.data.minimumParticlesPerRelease *
      Math.max(species.length, 1)
    return Math.max(10_000, Math.ceil(required / 10_000) * 10_000)
  }, [capabilities.data, durationHours, modelledEvents.length, species.length])

  useEffect(() => {
    if (
      capabilities.data &&
      minimumParticleBudget <= capabilities.data.maximumParticles
    ) {
      setParticles((current) => Math.max(current, minimumParticleBudget))
    }
  }, [capabilities.data, minimumParticleBudget])

  if (!open) return null

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (step < 3) {
      if (step === 2 && particles < minimumParticleBudget) {
        setError(
          `Use at least ${minimumParticleBudget.toLocaleString()} particles for the selected fires, duration, and species.`,
        )
        return
      }
      setError('')
      setStep((value) => value + 1)
      return
    }
    setError('')
    if (!start || !end || durationHours <= 0 || durationHours > 24) {
      setError('Choose a positive time window no longer than 24 hours.')
      return
    }
    if (species.length === 0) {
      setError('Select at least one transported species.')
      return
    }
    if (particles < minimumParticleBudget) {
      setError(
        `Use at least ${minimumParticleBudget.toLocaleString()} particles for the selected fires, duration, and species.`,
      )
      return
    }
    if (!modelledEvents.length) {
      setError(
        fireWeatherMode === 'automatic_cwfis'
          ? 'No fire events in this extent have archived NRCan CWFIS state. Use a Canadian extent or a reviewed manual override.'
          : 'No reconciled fire events fall inside this extent and time range.',
      )
      return
    }
    const config: SmokeScenarioConfigInput = {
      name,
      start_time: iso(start),
      end_time: iso(end),
      bbox,
      event_ids: modelledEvents.map((item) => item.event_id),
      area_mode: 'cffeps_native_growth',
      area_curve: [],
      fire_weather_mode: fireWeatherMode,
      fire_weather:
        fireWeatherMode === 'manual' ? { ffmc, dmc, dc } : null,
      species,
      uncertainty,
      grid_spacing_degrees: spacing,
      particle_budget: particles,
      random_seed: 20260722,
    }
    try {
      setSubmitting(true)
      onSubmitted(await smokeApi.createScenarioAndRun(name, config))
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : 'Unable to submit the run.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="smoke-modal-backdrop" role="presentation">
      <form className="smoke-builder" onSubmit={submit}>
        <div className="smoke-builder-heading">
          <div>
            <p className="eyebrow">CFFEPS → FLEXPART</p>
            <h2>Build smoke run</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close smoke run builder"
          >
            ×
          </button>
        </div>
        <ol className="smoke-steps" aria-label="Smoke run steps">
          {['Domain', 'Fires', 'Model', 'Review'].map((label, index) => (
            <li
              className={index === step ? 'active' : index < step ? 'done' : ''}
              key={label}
            >
              <span>{index + 1}</span>
              {label}
            </li>
          ))}
        </ol>

        {step === 0 && (
          <section className="smoke-builder-page">
            <label>
              Scenario name
              <input
                value={name}
                maxLength={100}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <div className="smoke-form-grid">
              <label>
                Start (UTC)
                <input
                  type="datetime-local"
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                />
              </label>
              <label>
                End (UTC)
                <input
                  type="datetime-local"
                  value={end}
                  onChange={(event) => setEnd(event.target.value)}
                />
              </label>
            </div>
            <p className="smoke-help">
              Latest complete GFS cycle:{' '}
              {capabilities.data?.latestCompleteGfsCycle ?? 'checking archive…'}{' '}
              · {durationHours.toFixed(0)} h window
            </p>
            <fieldset>
              <legend>Current map extent · west, south, east, north</legend>
              <div className="smoke-form-grid bbox-grid">
                {bbox.map((value, index) => (
                  <input
                    aria-label={['West', 'South', 'East', 'North'][index]}
                    key={index}
                    type="number"
                    step="0.01"
                    value={value}
                    onChange={(event) => {
                      const next = [...bbox] as Bbox
                      next[index] = Number(event.target.value)
                      setBbox(next)
                    }}
                  />
                ))}
              </div>
            </fieldset>
          </section>
        )}

        {step === 1 && (
          <section className="smoke-builder-page">
            <div className="smoke-source-summary">
              <strong>
                {eventQuery.data?.items.length ?? 0} reconciled fire events
              </strong>
              <span>
                Eligible fires observed during the run or its 24-hour source
                lookback will be frozen into this revision.
              </span>
            </div>
            {eventQuery.isLoading && (
              <p className="smoke-help">Matching current fire detections…</p>
            )}
            {eventQuery.error && (
              <p className="smoke-error">{eventQuery.error.message}</p>
            )}
            <h3>Fire-weather state</h3>
            <p className="smoke-help">
              By default each fire uses FFMC, DMC, and DC sampled from the
              archived NRCan CWFIS grid for its location and observation date.
              The exact grid checksum and cell are frozen with the run.
            </p>
            <fieldset>
              <legend>CFFDRS source</legend>
              <div className="smoke-choice-row">
                <label>
                  <input
                    type="radio"
                    name="fire-weather-mode"
                    checked={fireWeatherMode === 'automatic_cwfis'}
                    onChange={() => setFireWeatherMode('automatic_cwfis')}
                  />
                  Automatic per fire (recommended)
                </label>
                <label>
                  <input
                    type="radio"
                    name="fire-weather-mode"
                    checked={fireWeatherMode === 'manual'}
                    onChange={() => setFireWeatherMode('manual')}
                  />
                  Manual override for all fires
                </label>
              </div>
            </fieldset>
            {fireWeatherMode === 'automatic_cwfis' && (
              <p className="cffdrs-assumption">
                {eventQuery.data?.items.filter(
                  (item) => item.model_eligible && item.fire_weather,
                ).length ?? 0}{' '}
                of {eventQuery.data?.items.length ?? 0} selected events have a
                frozen CWFIS state. Events outside Canadian CWFIS coverage or
                without a CFFEPS-supported fuel are excluded.
              </p>
            )}
            {fireWeatherMode === 'manual' && (
              <>
                <p className="smoke-help">
                  FFMC, DMC, and DC are unitless moisture codes, not
                  percentages. Higher values mean drier fuels. This override is
                  applied to every selected fire and recorded as a manual
                  scientific assumption.
                </p>
                <div className="cffdrs-fields">
              <label className="cffdrs-field" htmlFor="cffdrs-ffmc">
                <span className="cffdrs-field-heading">
                  <strong>FFMC</strong>
                  <span>Fine Fuel Moisture Code</span>
                  <em>unitless code</em>
                </span>
                <input
                  id="cffdrs-ffmc"
                  type="number"
                  min="0.1"
                  max="101"
                  step="0.1"
                  value={ffmc}
                  aria-describedby="cffdrs-ffmc-help"
                  onChange={(event) => setFfmc(Number(event.target.value))}
                />
                <small id="cffdrs-ffmc-help">
                  Surface litter and other cured fine fuels. Indicates ease of
                  ignition and fine-fuel flammability. Accepted: 0.1–101.
                </small>
              </label>
              <label className="cffdrs-field" htmlFor="cffdrs-dmc">
                <span className="cffdrs-field-heading">
                  <strong>DMC</strong>
                  <span>Duff Moisture Code</span>
                  <em>unitless code</em>
                </span>
                <input
                  id="cffdrs-dmc"
                  type="number"
                  min="0.1"
                  max="1000"
                  step="0.1"
                  value={dmc}
                  aria-describedby="cffdrs-dmc-help"
                  onChange={(event) => setDmc(Number(event.target.value))}
                />
                <small id="cffdrs-dmc-help">
                  Loosely compacted organic layers of moderate depth. Indicates
                  consumption in duff and medium-size woody material. Accepted:
                  0.1–1,000.
                </small>
              </label>
              <label className="cffdrs-field" htmlFor="cffdrs-dc">
                <span className="cffdrs-field-heading">
                  <strong>DC</strong>
                  <span>Drought Code</span>
                  <em>unitless code</em>
                </span>
                <input
                  id="cffdrs-dc"
                  type="number"
                  min="0.1"
                  max="2000"
                  step="0.1"
                  value={dc}
                  aria-describedby="cffdrs-dc-help"
                  onChange={(event) => setDc(Number(event.target.value))}
                />
                <small id="cffdrs-dc-help">
                  Deep, compact organic layers. Indicates seasonal drought and
                  the potential for smouldering in deep duff and large logs.
                  Accepted: 0.1–2,000.
                </small>
              </label>
                </div>
                <p className="cffdrs-assumption">
                  The defaults (92 / 45 / 320) are only a research example.
                  Replace them with reviewed values for this date and domain.
                </p>
              </>
            )}
          </section>
        )}

        {step === 2 && (
          <section className="smoke-builder-page">
            <fieldset>
              <legend>Transported species</legend>
              <div className="smoke-choice-row">
                {speciesOptions.map((item) => (
                  <label key={item}>
                    <input
                      type="checkbox"
                      checked={species.includes(item)}
                      onChange={() =>
                        setSpecies((current) =>
                          current.includes(item)
                            ? current.filter((value) => value !== item)
                            : [...current, item],
                        )
                      }
                    />
                    {item === 'PM25' ? 'Primary PM2.5' : item}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="smoke-form-grid">
              <label>
                Uncertainty member
                <select
                  value={uncertainty}
                  onChange={(event) =>
                    setUncertainty(event.target.value as typeof uncertainty)
                  }
                >
                  <option value="low">Low</option>
                  <option value="central">Central</option>
                  <option value="high">High</option>
                </select>
              </label>
              <label>
                Grid spacing
                <select
                  value={spacing}
                  onChange={(event) =>
                    setSpacing(Number(event.target.value) as typeof spacing)
                  }
                >
                  <option value="1">1°</option>
                  <option value="0.5">0.5°</option>
                  <option value="0.25">0.25°</option>
                </select>
              </label>
            </div>
            <label>
              Particle budget
              <input
                type="number"
                min={minimumParticleBudget}
                max={capabilities.data?.maximumParticles ?? 1_000_000}
                step="10000"
                value={particles}
                onChange={(event) => setParticles(Number(event.target.value))}
              />
            </label>
            <p className="smoke-help">
              CFFEPS plume rise · species run separately so aerosol settling and
              scavenging remain enabled. Minimum for this scenario:{' '}
              {minimumParticleBudget.toLocaleString()} particles.
            </p>
          </section>
        )}

        {step === 3 && (
          <section className="smoke-builder-page review">
            <h3>{name}</h3>
            <dl>
              <div>
                <dt>Window</dt>
                <dd>{durationHours.toFixed(0)} hours</dd>
              </div>
              <div>
                <dt>Fire events</dt>
                <dd>
                  {modelledEvents.length} modelled
                  {modelledEvents.length !== (eventQuery.data?.items.length ?? 0)
                    ? ` · ${(eventQuery.data?.items.length ?? 0) - modelledEvents.length} excluded by source-time, fuel, or CWFIS checks`
                    : ''}
                </dd>
              </div>
              <div>
                <dt>CFFDRS state</dt>
                <dd>
                  {fireWeatherMode === 'automatic_cwfis'
                    ? 'NRCan CWFIS · dated grid sample per fire'
                    : `Manual override · FFMC ${ffmc} · DMC ${dmc} · DC ${dc}`}
                </dd>
              </div>
              <div>
                <dt>Species</dt>
                <dd>{species.join(', ')}</dd>
              </div>
              <div>
                <dt>Member</dt>
                <dd>{uncertainty}</dd>
              </div>
              <div>
                <dt>Resolution</dt>
                <dd>{spacing}°</dd>
              </div>
              <div>
                <dt>Particles</dt>
                <dd>{particles.toLocaleString()}</dd>
              </div>
            </dl>
            <div className="smoke-caveat">
              Research estimate of primary wildfire emissions. This is not an
              official air-quality forecast and does not model secondary aerosol
              chemistry.
            </div>
            {!capabilities.data?.writesEnabled && (
              <p className="smoke-warning">
                Submission is currently locked by SIMULATION_WRITES_ENABLED
                while scientific validation is pending. The complete scenario
                can still be reviewed here.
              </p>
            )}
            {capabilities.data?.writesEnabled && (
              <p className="smoke-warning">
                Interactive execution is enabled for research use. The current
                emission-factor registry is still pending independent review,
                so the output must not be treated as an official forecast.
              </p>
            )}
          </section>
        )}

        {error && <p className="smoke-error">{error}</p>}
        <div className="smoke-builder-actions">
          <button
            className="text-button"
            type="button"
            onClick={() =>
              step === 0 ? onClose() : setStep((value) => value - 1)
            }
          >
            {step === 0 ? 'Cancel' : 'Back'}
          </button>
          <button
            className="smoke-primary-button"
            type="submit"
            disabled={
              submitting ||
              capabilities.isLoading ||
              (step === 3 && !capabilities.data?.writesEnabled)
            }
          >
            {step === 3
              ? submitting
                ? 'Submitting…'
                : 'Submit run'
              : 'Continue'}
          </button>
        </div>
      </form>
    </div>
  )
}
