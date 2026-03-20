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
async def app_lifespan():
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
    return ctx.request_context.lifespan_state["client"]


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
