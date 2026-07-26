import calendar as _calendar
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.exceptions import NotFoundError
from app.core.utils import now_utc
from app.models.calendar_event import CalendarEvent
from app.models.milestone import Milestone
from app.models.project import Project
from app.models.task import Task
from app.schemas.calendar_event import CalendarItem, ProjectCalendar


def _windowed(stmt, column, date_from: Optional[str], date_to: Optional[str]):
    """#103: apply `_in_range` as SQL so the window bounds the rows fetched.

    `build_calendar` used to load every task and milestone in the project and
    throw most of them away in Python. `substr(col, 1, 10)` is the same 10-char
    date-prefix comparison `_in_range` does, so the semantics are identical —
    which is why the Python check stays in place as the guarantee of that, and
    catches the empty-string case SQL's `IS NOT NULL` does not.

    Only the dated rows can be filtered this way. Calendar *events* are excluded
    on purpose: a recurring event whose base date sits before the window still
    produces occurrences inside it, so narrowing that query would drop them.
    """
    stmt = stmt.where(column.is_not(None))
    day = func.substr(column, 1, 10)
    if date_from:
        stmt = stmt.where(day >= date_from)
    if date_to:
        stmt = stmt.where(day <= date_to)
    return stmt


def _in_range(start_at: str, date_from: Optional[str], date_to: Optional[str]) -> bool:
    """Range filter on the date portion (YYYY-MM-DD) of an ISO start value.

    Comparing the 10-char date prefix keeps date-only and datetime values (and
    all-day vs timed items) on the same footing. `date_from`/`date_to` are
    inclusive YYYY-MM-DD bounds; either may be omitted.
    """
    day = start_at[:10]
    if date_from and day < date_from:
        return False
    if date_to and day > date_to:
        return False
    return True


# ── Recurrence expansion ──────────────────────────────────────────────────────
# Minimal by design: daily / weekly / monthly with an optional until-date. No
# intervals, BYDAY, or per-occurrence exceptions.
# ponytail: MAX_OCCURRENCES caps a runaway (e.g. a daily event exported with no
# window and no until) at ~3 years; lift it or add real RRULE if that bites.
_MAX_OCCURRENCES = 1200


def _parse_day(iso: str) -> date:
    return date.fromisoformat(iso[:10])


def _shift_iso(iso: str, delta_days: int) -> str:
    """Shift only the date portion of an ISO value, preserving any time suffix."""
    shifted = _parse_day(iso) + timedelta(days=delta_days)
    return shifted.isoformat() + iso[10:]


def _add_months(d: date, n: int) -> date:
    total = d.month - 1 + n
    year = d.year + total // 12
    month = total % 12 + 1
    last = _calendar.monthrange(year, month)[1]  # clamp e.g. Jan 31 -> Feb 28
    return date(year, month, min(d.day, last))


def _first_on_or_after(base: date, recurrence: str, win_from: Optional[date]) -> date:
    """Fast-forward the first occurrence into the window so iteration is bounded
    by the window size, not by how far `base` is in the past."""
    if win_from is None or base >= win_from:
        return base
    if recurrence == "daily":
        return win_from
    if recurrence == "weekly":
        weeks = ((win_from - base).days + 6) // 7
        return base + timedelta(days=weeks * 7)
    # monthly — step months (few iterations)
    cur = base
    while cur < win_from:
        cur = _add_months(cur, 1)
    return cur


def _occurrence_dates(
    base: date,
    recurrence: str,
    until: Optional[date],
    win_from: Optional[date],
    win_to: Optional[date],
) -> list[date]:
    if recurrence == "none":
        return [base]
    out: list[date] = []
    cur = _first_on_or_after(base, recurrence, win_from)
    for _ in range(_MAX_OCCURRENCES):
        if until and cur > until:
            break
        if win_to and cur > win_to:
            break
        out.append(cur)
        if recurrence == "daily":
            cur += timedelta(days=1)
        elif recurrence == "weekly":
            cur += timedelta(days=7)
        elif recurrence == "monthly":
            cur = _add_months(cur, 1)
        else:
            break
    return out


def _event_items(
    ev: CalendarEvent, win_from: Optional[date], win_to: Optional[date],
    date_from: Optional[str], date_to: Optional[str],
) -> list[CalendarItem]:
    if ev.recurrence == "none" or not ev.recurrence:
        if not _in_range(ev.start_at, date_from, date_to):
            return []
        return [_make_event_item(ev, ev.start_at, ev.end_at, recurring=False)]

    base = _parse_day(ev.start_at)
    until = date.fromisoformat(ev.recurrence_until) if ev.recurrence_until else None
    items: list[CalendarItem] = []
    for occ in _occurrence_dates(base, ev.recurrence, until, win_from, win_to):
        delta = (occ - base).days
        items.append(
            _make_event_item(
                ev,
                _shift_iso(ev.start_at, delta),
                _shift_iso(ev.end_at, delta) if ev.end_at else None,
                recurring=True,
                occ_suffix=occ.isoformat(),
            )
        )
    return items


def _make_event_item(
    ev: CalendarEvent, start_at: str, end_at: Optional[str],
    recurring: bool, occ_suffix: Optional[str] = None,
) -> CalendarItem:
    item_id = f"event:{ev.id}:{occ_suffix}" if occ_suffix else f"event:{ev.id}"
    return CalendarItem(
        id=item_id,
        source="event",
        ref_id=ev.id,
        title=ev.title,
        start_at=start_at,
        end_at=end_at,
        all_day=ev.all_day,
        status=ev.status,
        phase_id=ev.phase_id,
        recurring=recurring,
    )


def build_calendar(
    session: Session,
    project_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> ProjectCalendar:
    if session.get(Project, project_id) is None:
        raise NotFoundError(f"project '{project_id}' not found")

    win_from = date.fromisoformat(date_from) if date_from else None
    win_to = date.fromisoformat(date_to) if date_to else None

    items: list[CalendarItem] = []

    for ev in session.exec(
        select(CalendarEvent).where(CalendarEvent.project_id == project_id)
    ).all():
        items.extend(_event_items(ev, win_from, win_to, date_from, date_to))

    for ms in session.exec(
        _windowed(
            select(Milestone).where(Milestone.project_id == project_id),
            Milestone.target_date,  # type: ignore[arg-type]
            date_from,
            date_to,
        )
    ).all():
        if not ms.target_date or not _in_range(ms.target_date, date_from, date_to):
            continue
        items.append(
            CalendarItem(
                id=f"milestone:{ms.id}",
                source="milestone",
                ref_id=ms.id,
                title=ms.title,
                start_at=ms.target_date,
                end_at=None,
                all_day=True,
                status=ms.status,
                phase_id=ms.phase_id,
            )
        )

    for tk in session.exec(
        _windowed(
            select(Task).where(Task.project_id == project_id),
            Task.due_at,  # type: ignore[arg-type]
            date_from,
            date_to,
        )
    ).all():
        if not tk.due_at or not _in_range(tk.due_at, date_from, date_to):
            continue
        items.append(
            CalendarItem(
                id=f"task:{tk.id}",
                source="task",
                ref_id=tk.id,
                title=tk.title,
                start_at=tk.due_at,
                end_at=None,
                all_day=True,
                status=tk.status,
                phase_id=tk.phase_id,
            )
        )

    items.sort(key=lambda it: (it.start_at, it.title))
    return ProjectCalendar(
        project_id=project_id, generated_at=now_utc(), items=items
    )


# ── iCalendar (.ics) export ───────────────────────────────────────────────────
# ponytail: hand-rolled VCALENDAR text (no `ics` dependency). No line folding at
# 75 octets and no VTIMEZONE — timed events export as floating local time, which
# matches how they're stored. Add both if a strict consumer complains.


def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _ics_compact(iso: str) -> str:
    """`YYYY-MM-DDTHH:MM:SS...` -> `YYYYMMDDTHHMMSS` (drops offset/fraction)."""
    d = iso[:10].replace("-", "")
    t = iso[11:19].replace(":", "") if len(iso) > 10 else ""
    return f"{d}T{t}" if t else d


def _ics_dt_line(name: str, iso: str, all_day: bool) -> str:
    if all_day or len(iso) <= 10:
        return f"{name};VALUE=DATE:{iso[:10].replace('-', '')}"
    return f"{name}:{_ics_compact(iso)}"


def _vevent(it: CalendarItem, dtstamp: str) -> list[str]:
    out = [
        "BEGIN:VEVENT",
        f"UID:{it.id}@planarus",
        f"DTSTAMP:{dtstamp}",
        _ics_dt_line("DTSTART", it.start_at, it.all_day),
    ]
    if it.end_at:
        out.append(_ics_dt_line("DTEND", it.end_at, it.all_day))
    out.append(f"SUMMARY:{_ics_escape(it.title)}")
    if it.source == "event" and it.status:
        out.append(f"STATUS:{it.status.upper()}")
    out.append("END:VEVENT")
    return out


def build_ics(
    session: Session,
    project_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> str:
    """Serialize the aggregated feed (events + milestones + tasks) to iCalendar."""
    cal = build_calendar(session, project_id, date_from, date_to)
    dtstamp = _ics_compact(now_utc()) + "Z"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Planarus//Calendar//EN",
        "CALSCALE:GREGORIAN",
    ]
    for it in cal.items:
        lines.extend(_vevent(it, dtstamp))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
