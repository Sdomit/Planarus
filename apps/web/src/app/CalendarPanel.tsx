import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type CalendarConnection, type CalendarItem } from '../api/client'
import {
  DAY_HOURS, MONTH_NAMES, WEEKDAY_NAMES, addDaysIso, addMonths, daySpan, dayKeyOf,
  isSameDay, isoDay, minutesIntoDay, monthMatrix, timeLabel, weekDays,
} from './date'
import './calendar-panel.css'

type ViewMode = 'month' | 'week' | 'day' | 'agenda'
const EVENT_STATUSES = ['confirmed', 'tentative', 'cancelled']
const RECURRENCES = ['none', 'daily', 'weekly', 'monthly']
const HOUR_PX = 44 // height of one hour row in the week/day time grid

type Source = CalendarItem['source']
interface Filters { event: boolean; milestone: boolean; task: boolean; hideCancelled: boolean }
const ALL_ON: Filters = { event: true, milestone: true, task: true, hideCancelled: false }

/** Deterministic, stable colour per phase (phases carry no colour of their own). */
function phaseColor(phaseId: string | null): string | null {
  if (!phaseId) return null
  let h = 0
  for (let i = 0; i < phaseId.length; i++) h = (h * 31 + phaseId.charCodeAt(i)) % 360
  return `hsl(${h} 55% 45%)`
}

function durationMin(it: CalendarItem): number {
  const s = minutesIntoDay(it.start_at)
  const e = minutesIntoDay(it.end_at)
  if (s == null) return 60
  if (e != null && e > s) return e - s
  return 60
}

interface EventDraft {
  id: string; title: string; all_day: boolean
  start_date: string; start_time: string; end_date: string; end_time: string
  status: string; location: string; description: string
  recurrence: string; recurrence_until: string
}

function emptyDraft(day: string): EventDraft {
  return {
    id: '', title: '', all_day: true, start_date: day, start_time: '09:00',
    end_date: '', end_time: '', status: 'confirmed', location: '', description: '',
    recurrence: 'none', recurrence_until: '',
  }
}

function splitIso(iso: string | null): { date: string; time: string } {
  if (!iso) return { date: '', time: '' }
  return { date: iso.slice(0, 10), time: iso.length > 10 ? iso.slice(11, 16) : '' }
}

function joinIso(date: string, time: string, allDay: boolean): string {
  if (!date) return ''
  return allDay || !time ? date : `${date}T${time}:00`
}

export default function CalendarPanel({ projectId, onOpenPlanning }: {
  projectId: string; onOpenPlanning?: () => void
}) {
  const today = new Date()
  const [view, setView] = useState<ViewMode>('month')
  const [anchor, setAnchor] = useState({ year: today.getFullYear(), month: today.getMonth(), day: today.getDate() })
  const [items, setItems] = useState<CalendarItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<EventDraft | null>(null)
  const [dragItem, setDragItem] = useState<CalendarItem | null>(null)
  const [overKey, setOverKey] = useState<string | null>(null)
  const [filters, setFilters] = useState<Filters>(ALL_ON)
  const [showSync, setShowSync] = useState(false)

  const anchorDate = new Date(anchor.year, anchor.month, anchor.day)

  const range = (() => {
    if (view === 'month') {
      const grid = monthMatrix(anchor.year, anchor.month)
      return { from: isoDay(grid[0][0]), to: isoDay(grid[5][6]) }
    }
    if (view === 'week') {
      const wk = weekDays(anchorDate)
      return { from: isoDay(wk[0]), to: isoDay(wk[6]) }
    }
    if (view === 'agenda') {
      const from = isoDay(anchorDate)
      return { from, to: addDaysIso(from, 45) }
    }
    const d = isoDay(anchorDate)
    return { from: d, to: d }
  })()

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const data = await api.calendar.get(projectId, { from: range.from, to: range.to })
      setItems(data.items)
    } catch {
      setError('Could not load the calendar.')
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, range.from, range.to])

  useEffect(() => { void load() }, [load])

  // Source + cancelled filtering applied everywhere the items are consumed.
  const visible = useMemo(() => items.filter(it =>
    filters[it.source] && !(filters.hideCancelled && it.status === 'cancelled'),
  ), [items, filters])

  const itemsForDay = useCallback((d: Date): CalendarItem[] => {
    const key = isoDay(d)
    return visible
      .filter(it => dayKeyOf(it.start_at) === key)
      .sort((a, b) => a.start_at.localeCompare(b.start_at) || a.title.localeCompare(b.title))
  }, [visible])

  // Month view: expand multi-day events so they appear on every day they cover.
  const monthMap = useMemo(() => {
    const map = new Map<string, { it: CalendarItem; seg: 'single' | 'start' | 'mid' | 'end' }[]>()
    for (const it of visible) {
      const span = daySpan(it.start_at, it.all_day ? it.end_at : null) // timed spans stay single-day
      for (let i = 0; i < span; i++) {
        const day = addDaysIso(it.start_at, i)
        const seg = span === 1 ? 'single' : i === 0 ? 'start' : i === span - 1 ? 'end' : 'mid'
        const list = map.get(day) ?? []
        list.push({ it, seg })
        map.set(day, list)
      }
    }
    for (const list of map.values()) list.sort((a, b) => a.it.start_at.localeCompare(b.it.start_at))
    return map
  }, [visible])

  // hour set (from clicking a time-grid slot) → a timed draft at that hour.
  function openCreate(day: string, hour?: number) {
    const d = emptyDraft(day)
    if (hour !== undefined) { d.all_day = false; d.start_time = `${String(hour).padStart(2, '0')}:00` }
    setDraft(d)
  }

  const openItem = useCallback(async (it: CalendarItem) => {
    if (it.source !== 'event') { onOpenPlanning?.(); return } // milestones/tasks live in Planning
    if (it.recurring) {
      // Load the base event so the dialog edits the true series (not a shifted occurrence).
      try {
        const base = (await api.calendarEvents.list(projectId)).find(e => e.id === it.ref_id)
        if (base) {
          const s = splitIso(base.start_at); const e = splitIso(base.end_at)
          setDraft({
            id: base.id, title: base.title, all_day: base.all_day,
            start_date: s.date, start_time: s.time || '09:00', end_date: e.date, end_time: e.time,
            status: base.status, location: base.location ?? '', description: base.description ?? '',
            recurrence: base.recurrence, recurrence_until: base.recurrence_until ?? '',
          })
          return
        }
      } catch { /* fall through */ }
    }
    const s = splitIso(it.start_at); const e = splitIso(it.end_at)
    setDraft({
      id: it.ref_id, title: it.title, all_day: it.all_day,
      start_date: s.date, start_time: s.time || '09:00', end_date: e.date, end_time: e.time,
      status: it.status ?? 'confirmed', location: '', description: '',
      recurrence: 'none', recurrence_until: '',
    })
  }, [projectId, onOpenPlanning])

  const reschedule = useCallback(async (it: CalendarItem, day: string) => {
    if (it.recurring) { setError('Recurring events are moved from the event dialog.'); return }
    try {
      if (it.source === 'milestone') await api.milestones.update(it.ref_id, { target_date: day })
      else if (it.source === 'task') await api.tasks.update(it.ref_id, { due_at: day })
      else {
        const start = it.all_day ? day : joinIso(day, it.start_at.slice(11, 16), false)
        await api.calendarEvents.update(it.ref_id, { start_at: start })
      }
      await load()
    } catch {
      setError('Could not move that item.')
    }
  }, [load])

  // Keyboard reschedule for a focused chip: ←/→ = ±1 day, ↑/↓ = ∓1 week.
  const nudge = useCallback((it: CalendarItem, deltaDays: number) => {
    if (it.recurring) return
    void reschedule(it, addDaysIso(dayKeyOf(it.start_at), deltaDays))
  }, [reschedule])

  function shiftView(dir: -1 | 1) {
    if (view === 'month') { setAnchor(a => ({ ...addMonths(a.year, a.month, dir), day: 1 })); return }
    const step = view === 'week' ? 7 : view === 'agenda' ? 45 : 1
    const d = new Date(anchor.year, anchor.month, anchor.day + dir * step)
    setAnchor({ year: d.getFullYear(), month: d.getMonth(), day: d.getDate() })
  }

  function goToday() {
    const n = new Date()
    setAnchor({ year: n.getFullYear(), month: n.getMonth(), day: n.getDate() })
  }

  const heading = view === 'month'
    ? `${MONTH_NAMES[anchor.month]} ${anchor.year}`
    : view === 'week'
      ? (() => { const wk = weekDays(anchorDate); return `${MONTH_NAMES[wk[0].getMonth()]} ${wk[0].getDate()} – ${wk[6].getDate()}, ${wk[6].getFullYear()}` })()
      : view === 'agenda'
        ? `Upcoming from ${anchorDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`
        : anchorDate.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })

  const gridProps = { itemsForDay, onCreate: openCreate, onOpen: openItem, onNudge: nudge, today,
    dragItem, setDragItem, overKey, setOverKey, onDropDay: reschedule }

  return (
    <div className="cal-panel">
      <div className="cal-toolbar">
        <div className="cal-nav">
          <button type="button" className="btn btn-outline btn-sm" onClick={() => shiftView(-1)} aria-label="Previous">‹</button>
          <button type="button" className="btn btn-outline btn-sm" onClick={goToday}>Today</button>
          <button type="button" className="btn btn-outline btn-sm" onClick={() => shiftView(1)} aria-label="Next">›</button>
          <span className="cal-heading">{heading}</span>
        </div>
        <div className="cal-toolbar-right">
          <FilterBar filters={filters} setFilters={setFilters} />
          <div className="ab-seg" role="group" aria-label="Calendar view">
            {(['month', 'week', 'day', 'agenda'] as ViewMode[]).map(v => (
              <button key={v} type="button" aria-pressed={view === v} className={view === v ? 'active' : ''} onClick={() => setView(v)}>
                {v[0].toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>
          <a className="btn btn-outline btn-sm" href={api.calendar.icsHref(projectId, range)} download title="Export the visible range as an .ics file">Export .ics</a>
          <button type="button" className="btn btn-outline btn-sm" onClick={() => setShowSync(true)} title="Connect Google/Microsoft calendars">Sync</button>
          <button type="button" className="btn btn-solid btn-sm" onClick={() => openCreate(isoDay(anchorDate))}>+ New event</button>
        </div>
      </div>

      {error && <p className="cal-error" role="alert">{error}</p>}
      {loading && items.length === 0 ? (
        <p className="cal-state">Loading…</p>
      ) : view === 'month' ? (
        <MonthGrid year={anchor.year} month={anchor.month} monthMap={monthMap} {...gridProps} />
      ) : view === 'agenda' ? (
        <AgendaList from={range.from} to={range.to} itemsForDay={itemsForDay} onOpen={openItem} today={today} />
      ) : (
        <TimeGrid days={view === 'week' ? weekDays(anchorDate) : [anchorDate]} {...gridProps} />
      )}

      {draft && (
        <EventDialog projectId={projectId} draft={draft}
          onClose={() => setDraft(null)} onSaved={() => { setDraft(null); void load() }} />
      )}
      {showSync && <CalendarSyncDialog projectId={projectId} onClose={() => setShowSync(false)} />}
    </div>
  )
}

// ── External sync (Google / Microsoft) ────────────────────────────────────
function CalendarSyncDialog({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [providers, setProviders] = useState<string[]>([])
  const [connections, setConnections] = useState<CalendarConnection[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  useEffect(() => { ref.current?.showModal?.() }, [])
  const close = () => ref.current?.close()

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const [p, c] = await Promise.all([
        api.calendarSync.providers(), api.calendarSync.connections(projectId),
      ])
      setProviders(p.providers); setConnections(c)
    } catch { setMsg('Could not load sync status.') } finally { setLoading(false) }
  }, [projectId])

  useEffect(() => { void refresh() }, [refresh])

  function connect(provider: string) {
    setMsg(null)
    api.calendarSync.connect(provider, projectId, api.calendarSync.callbackUrl(provider))
      .then(({ authorize_url }) => {
        const popup = window.open(authorize_url, 'calendar-oauth', 'width=520,height=680')
        // No postMessage channel — refresh once the OAuth popup closes.
        const timer = window.setInterval(() => {
          if (!popup || popup.closed) { window.clearInterval(timer); void refresh() }
        }, 1500)
      })
      .catch(e => setMsg(e instanceof Error ? e.message : String(e)))
  }

  async function runSync(id: string) {
    setBusy(id); setMsg(null)
    try {
      const r = await api.calendarSync.sync(id)
      setMsg(`Synced — pushed ${r.pushed}, pulled ${r.pulled}.`)
      await refresh()
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)) } finally { setBusy(null) }
  }

  async function disconnect(id: string) {
    setBusy(id); setMsg(null)
    try { await api.calendarSync.disconnect(id); await refresh() }
    catch (e) { setMsg(e instanceof Error ? e.message : String(e)) } finally { setBusy(null) }
  }

  return (
    <dialog ref={ref} className="cal-dialog" onClose={onClose} onClick={e => { if (e.target === ref.current) close() }}>
      <div className="cal-dialog-form">
        <div className="cal-dialog-head">
          <span className="cal-dialog-title">Calendar sync</span>
          <button type="button" className="btn btn-outline btn-sm" onClick={close} aria-label="Close">✕</button>
        </div>
        {loading ? <p className="cal-state">Loading…</p> : (
          <>
            {connections.length > 0 && (
              <div className="cal-sync-list">
                {connections.map(c => (
                  <div key={c.id} className="cal-sync-row">
                    <div style={{ minWidth: 0 }}>
                      <div className="cal-sync-acct">{c.provider} · {c.account_email}</div>
                      <div className="cal-sync-meta">
                        <span className={`cal-sync-status cal-sync-status--${c.status}`}>{c.status}</span>
                        {c.last_synced_at && <> · last synced {new Date(c.last_synced_at).toLocaleString()}</>}
                      </div>
                    </div>
                    <div className="cal-sync-actions">
                      <button type="button" className="btn btn-outline btn-xs" disabled={busy === c.id} onClick={() => runSync(c.id)}>Sync now</button>
                      <button type="button" className="btn btn-ghost btn-xs cal-del" disabled={busy === c.id} onClick={() => disconnect(c.id)}>Disconnect</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {providers.length > 0 ? (
              <div className="cal-sync-connect">
                {providers.map(p => (
                  <button key={p} type="button" className="btn btn-solid btn-sm" onClick={() => connect(p)}>
                    Connect {p[0].toUpperCase() + p.slice(1)}
                  </button>
                ))}
              </div>
            ) : (
              <p className="cal-state">
                External calendar sync isn’t configured on this server. It activates once a
                provider client ID and an encryption key are set in the environment.
              </p>
            )}
            {msg && <p className="cal-sync-msg" role="status">{msg}</p>}
          </>
        )}
      </div>
    </dialog>
  )
}

// ── Filters ───────────────────────────────────────────────────────────────
function FilterBar({ filters, setFilters }: { filters: Filters; setFilters: (f: Filters) => void }) {
  const toggle = (k: keyof Filters) => setFilters({ ...filters, [k]: !filters[k] })
  const SRC: { key: Source; label: string }[] = [
    { key: 'event', label: 'Events' }, { key: 'milestone', label: 'Milestones' }, { key: 'task', label: 'Tasks' },
  ]
  return (
    <div className="cal-filters" role="group" aria-label="Filters">
      {SRC.map(s => (
        <label key={s.key} className={`cal-filter cal-filter--${s.key}${filters[s.key] ? ' on' : ''}`}>
          <input type="checkbox" checked={filters[s.key]} onChange={() => toggle(s.key)} />
          <span>{s.label}</span>
        </label>
      ))}
      <label className={`cal-filter${filters.hideCancelled ? ' on' : ''}`}>
        <input type="checkbox" checked={filters.hideCancelled} onChange={() => toggle('hideCancelled')} />
        <span>Hide cancelled</span>
      </label>
    </div>
  )
}

// ── Chip (shared) ─────────────────────────────────────────────────────────
interface ChipCbs {
  onOpen: (it: CalendarItem) => void
  onNudge?: (it: CalendarItem, delta: number) => void
  setDragItem?: (it: CalendarItem | null) => void
}
function Chip({ it, seg = 'single', style, onOpen, onNudge, setDragItem }: ChipCbs & {
  it: CalendarItem; seg?: 'single' | 'start' | 'mid' | 'end'; style?: React.CSSProperties
}) {
  const timed = !it.all_day && it.start_at.length > 10
  const showText = seg === 'single' || seg === 'start'
  const dotColor = phaseColor(it.phase_id)
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!onNudge) return
    const map: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }
    if (e.key in map) { e.preventDefault(); onNudge(it, map[e.key]) }
  }
  return (
    <button
      type="button"
      className={`cal-chip cal-chip--${it.source} cal-chip--${seg}${it.status === 'cancelled' ? ' cal-chip--cancelled' : ''}`}
      style={style}
      draggable={!it.recurring && Boolean(setDragItem)}
      onDragStart={() => setDragItem?.(it)}
      onDragEnd={() => setDragItem?.(null)}
      onClick={(e) => { e.stopPropagation(); onOpen(it) }}
      onKeyDown={onKeyDown}
      title={`${it.title}${it.status ? ` · ${it.status}` : ''}${it.recurring ? ' · repeats' : ''}${onNudge && !it.recurring ? ' · arrow keys to move' : ''}`}
    >
      <span className="cal-chip-dot" aria-hidden="true" style={dotColor ? { background: dotColor } : undefined} />
      {showText && timed && <span className="cal-chip-time">{timeLabel(it.start_at)}</span>}
      {showText && <span className="cal-chip-title">{it.title}</span>}
      {showText && it.recurring && <span className="cal-chip-rec" aria-hidden="true">↻</span>}
    </button>
  )
}

// ── Month grid ────────────────────────────────────────────────────────────
interface GridBase {
  today: Date
  itemsForDay: (d: Date) => CalendarItem[]
  onCreate: (day: string, hour?: number) => void
  onOpen: (it: CalendarItem) => void
  onNudge: (it: CalendarItem, delta: number) => void
  dragItem: CalendarItem | null
  setDragItem: (it: CalendarItem | null) => void
  overKey: string | null
  setOverKey: (k: string | null) => void
  onDropDay: (it: CalendarItem, day: string) => void
}

function MonthGrid({ year, month, monthMap, today, onCreate, onOpen, onNudge, setDragItem, overKey, setOverKey, onDropDay, dragItem }:
  GridBase & { year: number; month: number; monthMap: Map<string, { it: CalendarItem; seg: 'single' | 'start' | 'mid' | 'end' }[]> }) {
  const weeks = monthMatrix(year, month)
  return (
    <div className="cal-month">
      <div className="cal-weekhead">
        {WEEKDAY_NAMES.map(w => <div key={w} className="cal-weekhead-cell">{w}</div>)}
      </div>
      <div className="cal-grid">
        {weeks.flat().map(d => {
          const key = isoDay(d)
          const dayItems = monthMap.get(key) ?? []
          const inMonth = d.getMonth() === month
          return (
            <div
              key={key}
              className={`cal-cell${inMonth ? '' : ' cal-cell--muted'}${isSameDay(d, today) ? ' cal-cell--today' : ''}${overKey === key ? ' cal-cell--over' : ''}`}
              onClick={() => onCreate(key)}
              title="Click to add an event"
              onDragOver={e => { if (dragItem) { e.preventDefault(); if (overKey !== key) setOverKey(key) } }}
              onDragLeave={() => setOverKey(overKey === key ? null : overKey)}
              onDrop={() => { if (dragItem) onDropDay(dragItem, key); setOverKey(null) }}
            >
              <div className="cal-cell-head">
                <button type="button" className="cal-daynum" onClick={(e) => { e.stopPropagation(); onCreate(key) }} aria-label={`Add event on ${key}`}>
                  {d.getDate()}
                </button>
              </div>
              <div className="cal-cell-items">
                {dayItems.map(({ it, seg }) => (
                  <Chip key={it.id + seg} it={it} seg={seg} onOpen={onOpen} onNudge={onNudge} setDragItem={setDragItem} />
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Week / day time grid ──────────────────────────────────────────────────
function TimeGrid({ days, today, itemsForDay, onCreate, onOpen, onNudge, setDragItem, overKey, setOverKey, onDropDay, dragItem }:
  GridBase & { days: Date[] }) {
  return (
    <div className={`cal-timegrid cal-timegrid--${days.length}`}>
      <div className="cal-tg-gutter">
        <div className="cal-tg-corner" />
        {DAY_HOURS.map(h => (
          <div key={h} className="cal-tg-hour" style={{ height: HOUR_PX }}>
            <span>{h === 0 ? '' : `${h % 12 === 0 ? 12 : h % 12}${h < 12 ? 'am' : 'pm'}`}</span>
          </div>
        ))}
      </div>
      {days.map(d => {
        const key = isoDay(d)
        const dayItems = itemsForDay(d)
        const allDay = dayItems.filter(it => minutesIntoDay(it.start_at) == null)
        const timed = dayItems.filter(it => minutesIntoDay(it.start_at) != null)
        // Lane packing so overlapping events sit side by side.
        const sorted = [...timed].sort((a, b) => (minutesIntoDay(a.start_at)! - minutesIntoDay(b.start_at)!))
        const laneEnds: number[] = []
        const placed = sorted.map(it => {
          const s = minutesIntoDay(it.start_at)!; const e = s + durationMin(it)
          let lane = laneEnds.findIndex(end => end <= s)
          if (lane === -1) { lane = laneEnds.length; laneEnds.push(e) } else laneEnds[lane] = e
          return { it, lane, s, e }
        })
        const lanes = Math.max(1, laneEnds.length)
        return (
          <div key={key} className={`cal-tg-day${isSameDay(d, today) ? ' cal-tg-day--today' : ''}${overKey === key ? ' cal-tg-day--over' : ''}`}>
            <div className="cal-tg-dayhead">
              <span className="cal-col-name">{WEEKDAY_NAMES[d.getDay()]}</span>
              <button type="button" className={`cal-daynum${isSameDay(d, today) ? ' cal-daynum--today' : ''}`} onClick={() => onCreate(key)} aria-label={`Add event on ${key}`}>
                {d.getDate()}
              </button>
            </div>
            <div className="cal-tg-allday" title="Click to add an all-day event"
              onClick={() => onCreate(key)}
              onDragOver={e => { if (dragItem) { e.preventDefault(); if (overKey !== key) setOverKey(key) } }}
              onDragLeave={() => setOverKey(overKey === key ? null : overKey)}
              onDrop={() => { if (dragItem) onDropDay(dragItem, key); setOverKey(null) }}>
              {allDay.length === 0
                ? <span className="cal-tg-allday-empty">—</span>
                : allDay.map(it => <Chip key={it.id} it={it} onOpen={onOpen} onNudge={onNudge} setDragItem={setDragItem} />)}
            </div>
            <div className="cal-tg-body" style={{ height: DAY_HOURS.length * HOUR_PX }}
              title="Click a time slot to add an event"
              onClick={e => {
                if (e.target !== e.currentTarget) return // ignore clicks on events
                const y = e.clientY - e.currentTarget.getBoundingClientRect().top
                onCreate(key, Math.min(23, Math.max(0, Math.floor(y / HOUR_PX))))
              }}>
              {DAY_HOURS.map(h => <div key={h} className="cal-tg-line" style={{ top: h * HOUR_PX }} />)}
              {placed.map(({ it, lane, s, e }) => (
                <button
                  key={it.id}
                  type="button"
                  className={`cal-tg-event cal-chip--${it.source}${it.status === 'cancelled' ? ' cal-chip--cancelled' : ''}`}
                  style={{
                    top: (s / 60) * HOUR_PX,
                    height: Math.max(((e - s) / 60) * HOUR_PX - 2, 16),
                    left: `calc(${(lane / lanes) * 100}% + 2px)`,
                    width: `calc(${100 / lanes}% - 4px)`,
                    borderLeftColor: phaseColor(it.phase_id) ?? undefined,
                  }}
                  draggable={!it.recurring}
                  onDragStart={() => setDragItem(it)}
                  onDragEnd={() => setDragItem(null)}
                  onClick={(ev) => { ev.stopPropagation(); onOpen(it) }}
                  title={`${it.title} · ${timeLabel(it.start_at)}`}
                >
                  <span className="cal-tg-event-time">{timeLabel(it.start_at)}</span>
                  <span className="cal-tg-event-title">{it.title}</span>
                </button>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Agenda list ───────────────────────────────────────────────────────────
function AgendaList({ from, to, itemsForDay, onOpen, today }: {
  from: string; to: string; itemsForDay: (d: Date) => CalendarItem[]; onOpen: (it: CalendarItem) => void; today: Date
}) {
  const days: Date[] = []
  for (let cur = from; cur <= to; cur = addDaysIso(cur, 1)) {
    const [y, m, d] = cur.split('-').map(Number)
    days.push(new Date(y, m - 1, d))
  }
  const rows = days.map(d => ({ d, items: itemsForDay(d) })).filter(r => r.items.length > 0)
  if (rows.length === 0) return <p className="cal-state">Nothing scheduled in this range.</p>
  return (
    <div className="cal-agenda">
      {rows.map(({ d, items }) => (
        <div key={isoDay(d)} className="cal-agenda-day">
          <div className={`cal-agenda-date${isSameDay(d, today) ? ' cal-agenda-date--today' : ''}`}>
            <span className="cal-agenda-dow">{WEEKDAY_NAMES[d.getDay()]}</span>
            <span className="cal-agenda-num">{d.getDate()}</span>
            <span className="cal-agenda-mon">{MONTH_NAMES[d.getMonth()].slice(0, 3)}</span>
          </div>
          <div className="cal-agenda-items">
            {items.map(it => <Chip key={it.id} it={it} onOpen={onOpen} />)}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Event dialog ──────────────────────────────────────────────────────────
function EventDialog({ projectId, draft, onClose, onSaved }: {
  projectId: string; draft: EventDraft; onClose: () => void; onSaved: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [form, setForm] = useState<EventDraft>(draft)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const editing = Boolean(form.id)

  useEffect(() => { ref.current?.showModal?.() }, [])
  const close = () => ref.current?.close()

  async function save(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true); setErr(null)
    const start = joinIso(form.start_date, form.start_time, form.all_day)
    const end = form.end_date ? joinIso(form.end_date, form.end_time, form.all_day) : null
    const payload = {
      title: form.title, start_at: start, end_at: end, all_day: form.all_day,
      status: form.status, location: form.location || undefined, description: form.description || undefined,
      recurrence: form.recurrence,
      recurrence_until: form.recurrence !== 'none' && form.recurrence_until ? form.recurrence_until : null,
    }
    try {
      if (editing) await api.calendarEvents.update(form.id, payload)
      else await api.calendarEvents.create(projectId, payload)
      onSaved()
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex))
    } finally {
      setSaving(false)
    }
  }

  async function remove() {
    if (!editing) return
    setSaving(true); setErr(null)
    try { await api.calendarEvents.remove(form.id); onSaved() }
    catch (ex) { setErr(ex instanceof Error ? ex.message : String(ex)) }
    finally { setSaving(false) }
  }

  return (
    <dialog ref={ref} className="cal-dialog" onClose={onClose} onClick={e => { if (e.target === ref.current) close() }}>
      <form className="cal-dialog-form" onSubmit={save}>
        <div className="cal-dialog-head">
          <span className="cal-dialog-title">{editing ? 'Edit event' : 'New event'}</span>
          <button type="button" className="btn btn-outline btn-sm" onClick={close} aria-label="Close">✕</button>
        </div>
        <input className="input" required placeholder="Event title" aria-label="Event title"
          value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
        <label className="cal-field-check">
          <input type="checkbox" checked={form.all_day} onChange={e => setForm(f => ({ ...f, all_day: e.target.checked }))} />
          <span>All day</span>
        </label>
        <div className="cal-field-row">
          <label className="cal-field">
            <span>Start</span>
            <input type="date" className="input input-sm" required value={form.start_date}
              onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))} />
          </label>
          {!form.all_day && (
            <label className="cal-field">
              <span>Time</span>
              <input type="time" className="input input-sm" value={form.start_time}
                onChange={e => setForm(f => ({ ...f, start_time: e.target.value }))} />
            </label>
          )}
        </div>
        <div className="cal-field-row">
          <label className="cal-field">
            <span>End</span>
            <input type="date" className="input input-sm" value={form.end_date}
              onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))} />
          </label>
          {!form.all_day && form.end_date && (
            <label className="cal-field">
              <span>Time</span>
              <input type="time" className="input input-sm" value={form.end_time}
                onChange={e => setForm(f => ({ ...f, end_time: e.target.value }))} />
            </label>
          )}
        </div>
        <div className="cal-field-row">
          <label className="cal-field">
            <span>Repeats</span>
            <select className="input select input-sm" value={form.recurrence}
              onChange={e => setForm(f => ({ ...f, recurrence: e.target.value }))}>
              {RECURRENCES.map(r => <option key={r} value={r}>{r === 'none' ? 'Does not repeat' : r}</option>)}
            </select>
          </label>
          {form.recurrence !== 'none' && (
            <label className="cal-field">
              <span>Until</span>
              <input type="date" className="input input-sm" value={form.recurrence_until}
                onChange={e => setForm(f => ({ ...f, recurrence_until: e.target.value }))} />
            </label>
          )}
        </div>
        <div className="cal-field-row">
          <label className="cal-field">
            <span>Status</span>
            <select className="input select input-sm" value={form.status}
              onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
              {EVENT_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="cal-field cal-field--grow">
            <span>Location</span>
            <input className="input input-sm" value={form.location}
              onChange={e => setForm(f => ({ ...f, location: e.target.value }))} />
          </label>
        </div>
        <label className="cal-field">
          <span>Description</span>
          <textarea className="input" rows={3} value={form.description}
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
        </label>
        {err && <p className="cal-error" role="alert">{err}</p>}
        <div className="cal-dialog-foot">
          {editing && (
            <button type="button" className="btn btn-outline btn-sm cal-del" onClick={remove} disabled={saving}>Delete</button>
          )}
          <div className="cal-dialog-foot-right">
            <button type="button" className="btn btn-outline btn-sm" onClick={close} disabled={saving}>Cancel</button>
            <button type="submit" className="btn btn-solid btn-sm" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
          </div>
        </div>
      </form>
    </dialog>
  )
}
