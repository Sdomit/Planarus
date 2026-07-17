import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type CalendarItem } from '../api/client'
import {
  MONTH_NAMES, WEEKDAY_NAMES, addMonths, dayKeyOf, isSameDay, isoDay,
  monthMatrix, timeLabel, weekDays,
} from './date'
import './calendar-panel.css'

type ViewMode = 'month' | 'week' | 'day'
const EVENT_STATUSES = ['confirmed', 'tentative', 'cancelled']

/** Draft used by the create/edit dialog. `id` empty ⇒ creating a new event. */
interface EventDraft {
  id: string
  title: string
  all_day: boolean
  start_date: string
  start_time: string
  end_date: string
  end_time: string
  status: string
  location: string
  description: string
}

function emptyDraft(day: string): EventDraft {
  return {
    id: '', title: '', all_day: true, start_date: day, start_time: '09:00',
    end_date: '', end_time: '', status: 'confirmed', location: '', description: '',
  }
}

/** Split an ISO value into its date + time (HH:MM) parts for the form inputs. */
function splitIso(iso: string | null): { date: string; time: string } {
  if (!iso) return { date: '', time: '' }
  const date = iso.slice(0, 10)
  const t = iso.length > 10 ? iso.slice(11, 16) : ''
  return { date, time: t }
}

/** Re-assemble the form's date + time (or just the date, when all-day). */
function joinIso(date: string, time: string, allDay: boolean): string {
  if (!date) return ''
  return allDay || !time ? date : `${date}T${time}:00`
}

export default function CalendarPanel({ projectId }: { projectId: string }) {
  const today = new Date()
  const [view, setView] = useState<ViewMode>('month')
  const [anchor, setAnchor] = useState({ year: today.getFullYear(), month: today.getMonth(), day: today.getDate() })
  const [items, setItems] = useState<CalendarItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<EventDraft | null>(null)
  const [dragItem, setDragItem] = useState<CalendarItem | null>(null)
  const [overKey, setOverKey] = useState<string | null>(null)

  const anchorDate = new Date(anchor.year, anchor.month, anchor.day)

  // Visible [from, to] range for the current view — drives the fetch.
  const range = (() => {
    if (view === 'month') {
      const grid = monthMatrix(anchor.year, anchor.month)
      return { from: isoDay(grid[0][0]), to: isoDay(grid[5][6]) }
    }
    if (view === 'week') {
      const wk = weekDays(anchorDate)
      return { from: isoDay(wk[0]), to: isoDay(wk[6]) }
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

  const itemsForDay = (d: Date): CalendarItem[] => {
    const key = isoDay(d)
    return items
      .filter(it => dayKeyOf(it.start_at) === key)
      .sort((a, b) => a.start_at.localeCompare(b.start_at) || a.title.localeCompare(b.title))
  }

  function openCreate(day: string) { setDraft(emptyDraft(day)) }

  function openEdit(it: CalendarItem) {
    if (it.source !== 'event') return // milestones/tasks are edited from Planning; here they only reschedule
    const s = splitIso(it.start_at)
    const e = splitIso(it.end_at)
    setDraft({
      id: it.ref_id, title: it.title, all_day: it.all_day,
      start_date: s.date, start_time: s.time || '09:00',
      end_date: e.date, end_time: e.time,
      status: it.status ?? 'confirmed', location: '', description: '',
    })
  }

  async function reschedule(it: CalendarItem, day: string) {
    try {
      if (it.source === 'milestone') {
        await api.milestones.update(it.ref_id, { target_date: day })
      } else if (it.source === 'task') {
        await api.tasks.update(it.ref_id, { due_at: day })
      } else {
        // Preserve the time-of-day for timed events; all-day events move by date.
        const start = it.all_day ? day : joinIso(day, it.start_at.slice(11, 16), false)
        await api.calendarEvents.update(it.ref_id, { start_at: start })
      }
      await load()
    } catch {
      setError('Could not move that item.')
    }
  }

  function shiftView(dir: -1 | 1) {
    if (view === 'month') {
      setAnchor(a => ({ ...addMonths(a.year, a.month, dir), day: 1 }))
    } else {
      const step = view === 'week' ? 7 : 1
      const d = new Date(anchor.year, anchor.month, anchor.day + dir * step)
      setAnchor({ year: d.getFullYear(), month: d.getMonth(), day: d.getDate() })
    }
  }

  function goToday() {
    const n = new Date()
    setAnchor({ year: n.getFullYear(), month: n.getMonth(), day: n.getDate() })
  }

  const heading = view === 'month'
    ? `${MONTH_NAMES[anchor.month]} ${anchor.year}`
    : view === 'week'
      ? (() => { const wk = weekDays(anchorDate); return `${MONTH_NAMES[wk[0].getMonth()]} ${wk[0].getDate()} – ${wk[6].getDate()}, ${wk[6].getFullYear()}` })()
      : anchorDate.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })

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
          <div className="ab-seg" role="group" aria-label="Calendar view">
            {(['month', 'week', 'day'] as ViewMode[]).map(v => (
              <button key={v} type="button" aria-pressed={view === v} className={view === v ? 'active' : ''} onClick={() => setView(v)}>
                {v[0].toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>
          <button type="button" className="btn btn-solid btn-sm" onClick={() => openCreate(isoDay(anchorDate))}>+ New event</button>
        </div>
      </div>

      {error && <p className="cal-error" role="alert">{error}</p>}
      {loading && items.length === 0 ? (
        <p className="cal-state">Loading…</p>
      ) : view === 'month' ? (
        <MonthGrid
          year={anchor.year} month={anchor.month} today={today}
          itemsForDay={itemsForDay} onCreate={openCreate} onOpen={openEdit}
          dragItem={dragItem} setDragItem={setDragItem} overKey={overKey} setOverKey={setOverKey}
          onDropDay={reschedule}
        />
      ) : (
        <DayColumns
          days={view === 'week' ? weekDays(anchorDate) : [anchorDate]} today={today}
          itemsForDay={itemsForDay} onCreate={openCreate} onOpen={openEdit}
          dragItem={dragItem} setDragItem={setDragItem} overKey={overKey} setOverKey={setOverKey}
          onDropDay={reschedule}
        />
      )}

      {draft && (
        <EventDialog
          projectId={projectId} draft={draft}
          onClose={() => setDraft(null)}
          onSaved={() => { setDraft(null); void load() }}
        />
      )}
    </div>
  )
}

interface GridProps {
  today: Date
  itemsForDay: (d: Date) => CalendarItem[]
  onCreate: (day: string) => void
  onOpen: (it: CalendarItem) => void
  dragItem: CalendarItem | null
  setDragItem: (it: CalendarItem | null) => void
  overKey: string | null
  setOverKey: (k: string | null) => void
  onDropDay: (it: CalendarItem, day: string) => void
}

function Chip({ it, onOpen, setDragItem }: {
  it: CalendarItem; onOpen: (it: CalendarItem) => void; setDragItem: (it: CalendarItem | null) => void
}) {
  const timed = !it.all_day && it.start_at.length > 10
  return (
    <button
      type="button"
      className={`cal-chip cal-chip--${it.source}${it.status === 'cancelled' ? ' cal-chip--cancelled' : ''}`}
      draggable
      onDragStart={() => setDragItem(it)}
      onDragEnd={() => setDragItem(null)}
      onClick={() => onOpen(it)}
      title={`${it.title}${it.status ? ` · ${it.status}` : ''}`}
    >
      <span className="cal-chip-dot" aria-hidden="true" />
      {timed && <span className="cal-chip-time">{timeLabel(it.start_at)}</span>}
      <span className="cal-chip-title">{it.title}</span>
    </button>
  )
}

function MonthGrid({ year, month, today, itemsForDay, onCreate, onOpen, setDragItem, overKey, setOverKey, onDropDay, dragItem }: GridProps & { year: number; month: number }) {
  const weeks = monthMatrix(year, month)
  return (
    <div className="cal-month">
      <div className="cal-weekhead">
        {WEEKDAY_NAMES.map(w => <div key={w} className="cal-weekhead-cell">{w}</div>)}
      </div>
      <div className="cal-grid">
        {weeks.flat().map(d => {
          const key = isoDay(d)
          const dayItems = itemsForDay(d)
          const inMonth = d.getMonth() === month
          return (
            <div
              key={key}
              className={`cal-cell${inMonth ? '' : ' cal-cell--muted'}${isSameDay(d, today) ? ' cal-cell--today' : ''}${overKey === key ? ' cal-cell--over' : ''}`}
              onDragOver={e => { if (dragItem) { e.preventDefault(); if (overKey !== key) setOverKey(key) } }}
              onDragLeave={() => setOverKey(overKey === key ? null : overKey)}
              onDrop={() => { if (dragItem) onDropDay(dragItem, key); setOverKey(null) }}
            >
              <div className="cal-cell-head">
                <button type="button" className="cal-daynum" onClick={() => onCreate(key)} aria-label={`Add event on ${key}`}>
                  {d.getDate()}
                </button>
              </div>
              <div className="cal-cell-items">
                {dayItems.map(it => <Chip key={it.id} it={it} onOpen={onOpen} setDragItem={setDragItem} />)}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function DayColumns({ days, today, itemsForDay, onCreate, onOpen, setDragItem, overKey, setOverKey, onDropDay, dragItem }: GridProps & { days: Date[] }) {
  return (
    <div className={`cal-cols cal-cols--${days.length}`}>
      {days.map(d => {
        const key = isoDay(d)
        const dayItems = itemsForDay(d)
        return (
          <div
            key={key}
            className={`cal-col${isSameDay(d, today) ? ' cal-col--today' : ''}${overKey === key ? ' cal-col--over' : ''}`}
            onDragOver={e => { if (dragItem) { e.preventDefault(); if (overKey !== key) setOverKey(key) } }}
            onDragLeave={() => setOverKey(overKey === key ? null : overKey)}
            onDrop={() => { if (dragItem) onDropDay(dragItem, key); setOverKey(null) }}
          >
            <div className="cal-col-head">
              <span className="cal-col-name">{WEEKDAY_NAMES[d.getDay()]}</span>
              <button type="button" className={`cal-daynum${isSameDay(d, today) ? ' cal-daynum--today' : ''}`} onClick={() => onCreate(key)} aria-label={`Add event on ${key}`}>
                {d.getDate()}
              </button>
            </div>
            <div className="cal-col-items">
              {dayItems.length === 0
                ? <p className="cal-col-empty">No items</p>
                : dayItems.map(it => <Chip key={it.id} it={it} onOpen={onOpen} setDragItem={setDragItem} />)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

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
    try {
      if (editing) {
        await api.calendarEvents.update(form.id, {
          title: form.title, start_at: start, end_at: end, all_day: form.all_day,
          status: form.status, location: form.location || undefined, description: form.description || undefined,
        })
      } else {
        await api.calendarEvents.create(projectId, {
          title: form.title, start_at: start, end_at: end, all_day: form.all_day,
          status: form.status, location: form.location || undefined, description: form.description || undefined,
        })
      }
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
    try {
      await api.calendarEvents.remove(form.id)
      onSaved()
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex))
    } finally {
      setSaving(false)
    }
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
