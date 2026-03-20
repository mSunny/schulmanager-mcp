#!/usr/bin/env python3
"""MCP Server for Schulmanager Online.

Provides tools to access school data: schedule, homework, exams, grades,
and parent letters via the Schulmanager Online platform.
"""

import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

from .api import SchulmanagerClient, SchulmanagerAPIError

# ── Lifespan: create & authenticate the client once ─────────────


@asynccontextmanager
async def app_lifespan(app):
    email = os.environ.get("SCHULMANAGER_EMAIL", "")
    password = os.environ.get("SCHULMANAGER_PASSWORD", "")
    if not email or not password:
        raise RuntimeError(
            "Set SCHULMANAGER_EMAIL and SCHULMANAGER_PASSWORD env vars"
        )

    client = SchulmanagerClient(email, password)
    await client.login()
    try:
        yield {"client": client}
    finally:
        await client.close()


mcp = FastMCP("schulmanager_mcp", lifespan=app_lifespan)


def _get_client(ctx: Context) -> SchulmanagerClient:
    return ctx.request_context.lifespan_context["client"]


def _default_student_id(client: SchulmanagerClient, student_id: int | None) -> int:
    """Resolve student ID – use the first child if none given."""
    if student_id is not None:
        return student_id
    if client.students:
        return client.students[0]["id"]
    raise SchulmanagerAPIError("No students found on this account")


def _format_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


# ── Input Models ────────────────────────────────────────────────


class ScheduleInput(BaseModel):
    """Input for fetching the class schedule."""
    model_config = ConfigDict(str_strip_whitespace=True)

    student_id: Optional[int] = Field(
        default=None,
        description="Student ID. Omit to use the first child on the account.",
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Start date (YYYY-MM-DD). Defaults to today.",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date (YYYY-MM-DD). Defaults to start + 6 days.",
    )


class StudentInput(BaseModel):
    """Input for student-specific queries (homework, grades)."""
    model_config = ConfigDict(str_strip_whitespace=True)

    student_id: Optional[int] = Field(
        default=None,
        description="Student ID. Omit to use the first child on the account.",
    )


class ExamsInput(BaseModel):
    """Input for fetching upcoming exams."""
    model_config = ConfigDict(str_strip_whitespace=True)

    student_id: Optional[int] = Field(
        default=None,
        description="Student ID. Omit to use the first child on the account.",
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Start date (YYYY-MM-DD). Defaults to today.",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date (YYYY-MM-DD). Defaults to start + 30 days.",
    )


# ── Tools ───────────────────────────────────────────────────────


@mcp.tool(
    name="schulmanager_get_students",
    annotations={
        "title": "List Students",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_students(ctx: Context) -> str:
    """List all children/students linked to this Schulmanager account.

    Returns student IDs, names, and class information. Use a student ID
    from this list for other tools if the account has multiple children.

    Returns:
        str: JSON array of student objects with id, firstName, lastName, className.
    """
    client = _get_client(ctx)
    await client.ensure_authenticated()
    if not client.students:
        return "No students found on this account."
    return _format_json(client.students)


@mcp.tool(
    name="schulmanager_get_schedule",
    annotations={
        "title": "Get Class Schedule",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_schedule(params: ScheduleInput, ctx: Context) -> str:
    """Fetch the class timetable/schedule for a student.

    Returns all lessons in the requested date range with subject,
    teacher, room, start/end times, and any substitution info.

    Args:
        params: Schedule query parameters (student_id, start_date, end_date).

    Returns:
        str: JSON with lesson data for the requested period.
    """
    client = _get_client(ctx)
    sid = _default_student_id(client, params.student_id)
    start = params.start_date or date.today().isoformat()
    end = params.end_date or (
        date.fromisoformat(start) + timedelta(days=6)
    ).isoformat()

    try:
        data = await client.get_schedule(sid, start, end)
        return _format_json(data)
    except Exception as e:
        return f"Error fetching schedule: {e}"


@mcp.tool(
    name="schulmanager_get_homework",
    annotations={
        "title": "Get Homework",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_homework(params: StudentInput, ctx: Context) -> str:
    """Fetch current homework assignments for a student.

    Returns all pending homework with subject, description, and due date.

    Args:
        params: Student query parameters (student_id).

    Returns:
        str: JSON with homework assignments.
    """
    client = _get_client(ctx)
    sid = _default_student_id(client, params.student_id)

    try:
        data = await client.get_homework(sid)
        return _format_json(data)
    except Exception as e:
        return f"Error fetching homework: {e}"


@mcp.tool(
    name="schulmanager_get_exams",
    annotations={
        "title": "Get Upcoming Exams",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_exams(params: ExamsInput, ctx: Context) -> str:
    """Fetch upcoming exams and tests for a student.

    Returns exam dates, subjects, types, and descriptions.

    Args:
        params: Exam query parameters (student_id, start_date, end_date).

    Returns:
        str: JSON with exam/test data.
    """
    client = _get_client(ctx)
    sid = _default_student_id(client, params.student_id)
    start = params.start_date or date.today().isoformat()
    end = params.end_date or (
        date.fromisoformat(start) + timedelta(days=30)
    ).isoformat()

    try:
        data = await client.get_exams(sid, start, end)
        return _format_json(data)
    except Exception as e:
        return f"Error fetching exams: {e}"


@mcp.tool(
    name="schulmanager_get_grades",
    annotations={
        "title": "Get Grades",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_grades(params: StudentInput, ctx: Context) -> str:
    """Fetch grades/marks for a student.

    Returns all recorded grades grouped by subject.

    Args:
        params: Student query parameters (student_id).

    Returns:
        str: JSON with grade data per subject.
    """
    client = _get_client(ctx)
    sid = _default_student_id(client, params.student_id)

    try:
        data = await client.get_grades(sid)
        return _format_json(data)
    except Exception as e:
        return f"Error fetching grades: {e}"


@mcp.tool(
    name="schulmanager_get_letters",
    annotations={
        "title": "Get Parent Letters",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_letters(ctx: Context) -> str:
    """Fetch parent letters and school notifications.

    Returns all letters/messages from the school including title,
    date, content, and whether confirmation is required.

    Returns:
        str: JSON with parent letter data.
    """
    client = _get_client(ctx)

    try:
        data = await client.get_letters()
        return _format_json(data)
    except Exception as e:
        return f"Error fetching letters: {e}"


@mcp.tool(
    name="schulmanager_get_institution",
    annotations={
        "title": "Get School Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_institution(ctx: Context) -> str:
    """Fetch information about the school/institution.

    Returns school name, address, and configuration details.

    Returns:
        str: JSON with institution data.
    """
    client = _get_client(ctx)

    try:
        data = await client.get_institution()
        return _format_json(data)
    except Exception as e:
        return f"Error fetching institution: {e}"


WEEKDAYS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
LETTER_BASE_URL = "https://login.schulmanager-online.de/#/modules/letters/view"


def _next_school_day(today: date) -> date:
    """Return the next school day (skip weekends)."""
    nxt = today + timedelta(days=1)
    while nxt.weekday() >= 5:  # 5=Sat, 6=Sun
        nxt += timedelta(days=1)
    return nxt



def _extract_result_data(result: Any) -> Any:
    """Extract the 'data' payload from an API batch result entry."""
    if isinstance(result, dict):
        return result.get("data", result)
    return result


def _format_daily_report(
    student: dict,
    tomorrow: date,
    schedule: list,
    homework: list,
    exams: list,
    letters: list,
) -> str:
    """Build a Markdown daily briefing for one student."""
    name = f"{student.get('firstname', '?')} {student.get('lastname', '')}"
    tom_str = tomorrow.strftime("%d.%m.%Y")
    wd = WEEKDAYS_DE[tomorrow.weekday()]

    # ── Gather all data first ────────────────────────────────────

    # Unread letters
    sid = student.get("id")
    unread = []
    for letter in letters:
        for st in letter.get("studentStatuses", []):
            if st.get("studentId") == sid and st.get("readTimestamp") is None:
                unread.append(letter)
                break

    # Tomorrow's lessons
    tom_iso = tomorrow.isoformat()
    tom_lessons = [l for l in schedule if l.get("date") == tom_iso]
    tom_lessons.sort(key=lambda l: int(l.get("classHour", {}).get("number", 0)))

    # Classify lessons
    cancellations = []
    substitutions = []
    regular_subjects = []
    for lesson in tom_lessons:
        lesson_type = lesson.get("type", "")
        if lesson.get("isCancelled") or lesson_type == "cancelledLesson":
            originals = lesson.get("originalLessons", [])
            subj = originals[0].get("subject", {}).get("name", "?") if originals else "?"
            cancellations.append(subj)
        else:
            actual = lesson.get("actualLesson", {})
            subj = actual.get("subject", {}).get("name") or actual.get("subjectLabel", "?")
            if lesson_type == "substitution":
                substitutions.append(subj)
            regular_subjects.append(subj)

    # Exams sorted
    exams_sorted = sorted(exams, key=lambda e: e.get("date", ""))

    # Homework – collect for next 7 days
    today = date.today()
    today_iso = today.isoformat()
    hw_end = today + timedelta(days=7)

    # Build list of the next 7 school days for grouping
    hw_days: list[date] = []
    d = _next_school_day(today)
    while d <= hw_end:
        hw_days.append(d)
        d = _next_school_day(d)

    # Homework "date" = day it was assigned; it's due the next school day.
    # Build mapping: due_date -> list of homework items
    hw_by_due: dict[str, list] = {}
    for h in homework:
        assigned = h.get("date", "")
        if not assigned:
            continue
        try:
            assigned_date = date.fromisoformat(assigned)
        except ValueError:
            continue
        due = _next_school_day(assigned_date)
        due_iso = due.isoformat()
        if due_iso not in hw_by_due:
            hw_by_due[due_iso] = []
        hw_by_due[due_iso].append(h)

    # Filter to only the next 7 days
    hw_week: list[tuple[date, list]] = []
    hw_total = 0
    for day in hw_days:
        items = hw_by_due.get(day.isoformat(), [])
        if items:
            hw_week.append((day, items))
            hw_total += len(items)

    # ── Build summary ("Auf einen Blick") ────────────────────────

    lines: list[str] = []
    lines.append(f"## {name}")
    lines.append("")

    summary_bullets: list[str] = []

    # Unread messages summary
    if unread:
        titles = ", ".join(f'"{l.get("title", "?")}"' for l in unread)
        summary_bullets.append(
            f"**{len(unread)} ungelesene Nachricht{'en' if len(unread) != 1 else ''}** -- {titles}"
        )

    # Schedule summary
    if tom_lessons:
        # Deduplicate subjects in order
        seen = set()
        unique_subjects = []
        for s in regular_subjects:
            if s not in seen:
                seen.add(s)
                unique_subjects.append(s)
        subj_str = ", ".join(unique_subjects)

        alerts = []
        if cancellations:
            n = len(cancellations)
            alerts.append(f"**{n}. Stunde faellt aus** ({', '.join(cancellations)})")
        if substitutions:
            n = len(substitutions)
            alerts.append(f"{n}x Vertretung ({', '.join(substitutions)})")

        if alerts:
            summary_bullets.append(
                f"Stundenplan {wd}: {'; '.join(alerts)}, danach {subj_str}"
            )
        else:
            summary_bullets.append(f"Stundenplan {wd}: {subj_str}")
    else:
        summary_bullets.append(f"**Kein Unterricht** am {wd}")

    # Exams summary
    if exams_sorted:
        exam_parts = []
        for ex in exams_sorted:
            ex_wd = WEEKDAYS_DE[date.fromisoformat(ex.get("date", today_iso)).weekday()]
            subj = ex.get("subject", {}).get("name", ex.get("subjectText", "?"))
            ex_type = ex.get("type", {}).get("name", "Test")
            exam_parts.append(f"{ex_wd} {subj} ({ex_type})")
        summary_bullets.append(
            f"**{len(exams_sorted)} Arbeit{'en' if len(exams_sorted) != 1 else ''} diese Woche** -- "
            + ", ".join(exam_parts)
        )

    # Homework summary
    if hw_total:
        # Highlight tomorrow's homework specifically, plus total
        hw_tomorrow = hw_by_due.get(tomorrow.isoformat(), [])
        if hw_tomorrow:
            hw_subj = ", ".join(h.get("subject", "?") for h in hw_tomorrow)
            summary_bullets.append(
                f"Hausaufgaben fuer {wd}: {hw_subj}"
                + (f" (+{hw_total - len(hw_tomorrow)} weitere diese Woche)" if hw_total > len(hw_tomorrow) else "")
            )
        else:
            summary_bullets.append(f"**{hw_total} Hausaufgaben** diese Woche (keine fuer {wd})")
    else:
        summary_bullets.append(f"Keine Hausaufgaben eingetragen")

    lines.append(f"### Auf einen Blick")
    for b in summary_bullets:
        lines.append(f"- {b}")
    lines.append("")

    # ── Detailed sections ────────────────────────────────────────

    # Letters detail
    lines.append(f"### Neue Nachrichten ({len(unread)})")
    if unread:
        for letter in unread:
            sent = letter.get("sentDate", "")[:10]
            lid = letter.get("id", "")
            link = f"{LETTER_BASE_URL}/{lid}" if lid else ""
            lines.append(
                f"- **{letter.get('title', '?')}** ({sent})"
                + (f"  \n  {link}" if link else "")
            )
    else:
        lines.append("- Keine ungelesenen Nachrichten")
    lines.append("")

    # Schedule detail
    lines.append(f"### Stundenplan {wd} {tom_str}")
    if tom_lessons:
        for lesson in tom_lessons:
            hour = lesson.get("classHour", {}).get("number", "?")
            lesson_type = lesson.get("type", "")

            if lesson.get("isCancelled") or lesson_type == "cancelledLesson":
                originals = lesson.get("originalLessons", [])
                if originals:
                    orig_subj = originals[0].get("subject", {}).get("name", "?")
                    lines.append(f"- **{hour}. Stunde**: ~~{orig_subj}~~ -- Entfall")
                else:
                    lines.append(f"- **{hour}. Stunde**: Entfall")
                continue

            actual = lesson.get("actualLesson", {})
            subj = actual.get("subject", {}).get("name") or actual.get("subjectLabel", "?")
            room = actual.get("room", {}).get("name", "")
            teachers = actual.get("teachers", [])
            teacher = teachers[0].get("lastname", "") if teachers else ""
            change = ""
            if lesson_type == "substitution":
                change = " (Vertretung)"
            room_str = f", Raum {room}" if room else ""
            teacher_str = f" ({teacher})" if teacher else ""
            lines.append(
                f"- **{hour}. Stunde**: {subj}{teacher_str}{room_str}{change}"
            )
    else:
        lines.append("- Kein Unterricht")
    lines.append("")

    # Exams detail
    lines.append("### Klassenarbeiten & Tests (naechste 7 Tage)")
    if exams_sorted:
        for ex in exams_sorted:
            ex_date = ex.get("date", "?")
            subj = ex.get("subject", {}).get("name", ex.get("subjectText", "?"))
            ex_type = ex.get("type", {}).get("name", "Test")
            comment = ex.get("comment", "")
            comment_str = f' -- "{comment}"' if comment else ""
            lines.append(f"- **{ex_date}**: {subj} ({ex_type}){comment_str}")
    else:
        lines.append("- Keine anstehenden Arbeiten")
    lines.append("")

    # Homework detail – next 7 days
    lines.append("### Hausaufgaben (naechste 7 Tage)")
    if hw_week:
        for hw_date, items in hw_week:
            hw_wd = WEEKDAYS_DE[hw_date.weekday()]
            hw_str = hw_date.strftime("%d.%m.")
            for h in items:
                lines.append(
                    f"- **{hw_wd} {hw_str} {h.get('subject', '?')}**: {h.get('homework', '')}"
                )
    else:
        lines.append("- Keine Hausaufgaben eingetragen")
    lines.append("")

    return "\n".join(lines)


@mcp.tool(
    name="schulmanager_daily_report",
    annotations={
        "title": "Daily Parent Briefing",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def daily_report(ctx: Context) -> str:
    """Generate a daily parent briefing for ALL children on this account.

    The report includes for each child:
    - Unread messages/letters from teachers
    - Tomorrow's class schedule (next school day, skips weekends)
    - Exams and tests in the next 7 days
    - Homework due in the next 7 days (grouped by day)

    This is the ideal tool for a quick morning or evening overview
    of everything school-related. No parameters needed -- it
    automatically covers all children and picks the right dates.

    Returns:
        str: Markdown-formatted daily briefing for all students.
    """
    client = _get_client(ctx)
    await client.ensure_authenticated()

    if not client.students:
        return "Keine Schueler auf diesem Account gefunden."

    today = date.today()
    tomorrow = _next_school_day(today)
    exam_end = (today + timedelta(days=7)).isoformat()

    # Fetch letters once (shared across all children)
    try:
        letters = await client.get_letters()
        if not isinstance(letters, list):
            letters = []
    except Exception:
        letters = []

    # Build a batch request for all children at once
    requests: list[dict] = []
    for student in client.students:
        sid = student["id"]
        requests.append({
            "moduleName": "schedules",
            "endpointName": "get-actual-lessons",
            "parameters": {
                "student": {"id": sid},
                "start": tomorrow.isoformat(),
                "end": tomorrow.isoformat(),
            },
        })
        requests.append({
            "moduleName": "classbook",
            "endpointName": "get-homework",
            "parameters": {"student": {"id": sid}},
        })
        requests.append({
            "moduleName": "exams",
            "endpointName": "get-exams",
            "parameters": {
                "student": {"id": sid},
                "start": today.isoformat(),
                "end": exam_end,
            },
        })

    try:
        results = await client.api_call(requests)
    except Exception as e:
        return f"Fehler beim Abrufen der Daten: {e}"

    # Parse results -- 3 results per student in order
    parts: list[str] = []
    parts.append(f"# Eltern-Briefing ({today.strftime('%d.%m.%Y')})")
    parts.append("")

    for i, student in enumerate(client.students):
        base = i * 3
        schedule = _extract_result_data(results[base]) if base < len(results) else []
        homework = _extract_result_data(results[base + 1]) if base + 1 < len(results) else []
        exams = _extract_result_data(results[base + 2]) if base + 2 < len(results) else []

        if not isinstance(schedule, list):
            schedule = []
        if not isinstance(homework, list):
            homework = []
        if not isinstance(exams, list):
            exams = []

        parts.append(
            _format_daily_report(student, tomorrow, schedule, homework, exams, letters)
        )

    return "\n".join(parts)


@mcp.tool(
    name="schulmanager_raw_call",
    annotations={
        "title": "Raw API Call",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def raw_call(module: str, endpoint: str, parameters: str, ctx: Context) -> str:
    """Make a raw API call to any Schulmanager endpoint.

    Use this for endpoints not covered by the other tools. The parameters
    argument is a JSON string that will be parsed and sent as the request body.

    Args:
        module: The module name (e.g. 'schedules', 'classbook', 'exams').
        endpoint: The endpoint name (e.g. 'get-actual-lessons').
        parameters: JSON string with request parameters (e.g. '{"student": {"id": 123}}').

    Returns:
        str: JSON response from the API.
    """
    client = _get_client(ctx)

    try:
        params = json.loads(parameters) if parameters else {}
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON in parameters: {e}"

    try:
        data = await client.single_call(module, endpoint, params)
        return _format_json(data)
    except Exception as e:
        return f"Error: {e}"


# ── Entry point ─────────────────────────────────────────────────


def main():
    mcp.run()


if __name__ == "__main__":
    main()
