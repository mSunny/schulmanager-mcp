#!/usr/bin/env python3
"""Print the daily parent briefing to stdout."""

import asyncio
import os
import sys

# Allow running from repo root without install
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from datetime import date, timedelta
from schulmanager_mcp.api import SchulmanagerClient
from schulmanager_mcp.server import (
    _next_school_day,
    _extract_result_data,
    _format_daily_report,
)


async def main():
    email = os.environ.get("SCHULMANAGER_EMAIL", "")
    password = os.environ.get("SCHULMANAGER_PASSWORD", "")
    if not email or not password:
        print("Bitte SCHULMANAGER_EMAIL und SCHULMANAGER_PASSWORD setzen.", file=sys.stderr)
        sys.exit(1)

    client = SchulmanagerClient(email, password)
    await client.login()

    today = date.today()
    tomorrow = _next_school_day(today)
    exam_end = (today + timedelta(days=7)).isoformat()

    letters = await client.get_letters()
    if not isinstance(letters, list):
        letters = []

    requests = []
    for student in client.students:
        sid = student["id"]
        requests.append({"moduleName": "schedules", "endpointName": "get-actual-lessons",
                         "parameters": {"student": {"id": sid}, "start": tomorrow.isoformat(), "end": tomorrow.isoformat()}})
        requests.append({"moduleName": "classbook", "endpointName": "get-homework",
                         "parameters": {"student": {"id": sid}}})
        requests.append({"moduleName": "exams", "endpointName": "get-exams",
                         "parameters": {"student": {"id": sid}, "start": today.isoformat(), "end": exam_end}})

    results = await client.api_call(requests)

    parts = [f"# Eltern-Briefing ({today.strftime('%d.%m.%Y')})", ""]
    for i, student in enumerate(client.students):
        base = i * 3
        schedule = _extract_result_data(results[base]) if base < len(results) else []
        homework = _extract_result_data(results[base + 1]) if base + 1 < len(results) else []
        exams = _extract_result_data(results[base + 2]) if base + 2 < len(results) else []
        if not isinstance(schedule, list): schedule = []
        if not isinstance(homework, list): homework = []
        if not isinstance(exams, list): exams = []
        parts.append(_format_daily_report(student, tomorrow, schedule, homework, exams, letters))

    print("\n".join(parts))
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
