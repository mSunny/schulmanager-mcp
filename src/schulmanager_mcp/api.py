"""Schulmanager Online API client.

Handles authentication (PBKDF2-SHA512 + JWT) and all API communication
with the Schulmanager Online platform.
"""

import hashlib
import json
import re
import time
from typing import Any

import httpx

API_BASE_URL = "https://login.schulmanager-online.de"
SALT_URL = f"{API_BASE_URL}/api/get-salt"
LOGIN_URL = f"{API_BASE_URL}/api/login"
CALLS_URL = f"{API_BASE_URL}/api/calls"

# PBKDF2 parameters matching Schulmanager's JS implementation
PBKDF2_ITERATIONS = 99999
PBKDF2_DK_LEN = 512  # 512 bytes = 4096 bits = 1024 hex chars


class SchulmanagerAPIError(Exception):
    """Raised when the Schulmanager API returns an error."""


class SchulmanagerClient:
    """Client for the Schulmanager Online API."""

    def __init__(self, email: str, password: str) -> None:
        self.email = email
        self.password = password
        self.token: str | None = None
        self.token_expiry: float = 0
        self.bundle_version: str = "3505280ee7"
        self.students: list[dict[str, Any]] = []
        self.institution_id: int | None = None
        self._http: httpx.AsyncClient | None = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ── Authentication ──────────────────────────────────────────────

    async def _fetch_bundle_version(self) -> str:
        """Extract the bundleVersion hash from Schulmanager's JS bundle."""
        try:
            client = await self._client()
            resp = await client.get(API_BASE_URL)
            resp.raise_for_status()
            html = resp.text

            # Look for JS bundle references
            js_matches = re.findall(r'src="(/[^"]*\.js[^"]*)"', html)
            for js_path in js_matches:
                js_resp = await client.get(f"{API_BASE_URL}{js_path}")
                if js_resp.status_code == 200:
                    # Look for bundleVersion pattern
                    version_match = re.search(
                        r'bundleVersion["\s:]+["\']([a-f0-9]{8,})["\']',
                        js_resp.text,
                    )
                    if version_match:
                        return version_match.group(1)
        except Exception:
            pass
        return self.bundle_version  # fallback

    async def _get_salt(self) -> str:
        """Retrieve the password salt from the API.

        The API returns the salt as a plain JSON string (not an object).
        """
        client = await self._client()
        resp = await client.post(
            SALT_URL,
            json={"emailOrUsername": self.email, "mobileApp": False},
        )
        resp.raise_for_status()
        data = resp.json()
        # API returns the salt directly as a string
        if isinstance(data, str):
            return data
        # Fallback if the format changed to an object
        return data.get("salt", data)

    @staticmethod
    def _generate_salted_hash(password: str, salt: str) -> str:
        """Generate PBKDF2-SHA512 hash matching Schulmanager's auth scheme."""
        dk = hashlib.pbkdf2_hmac(
            "sha512",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            PBKDF2_ITERATIONS,
            dklen=PBKDF2_DK_LEN,
        )
        return dk.hex()

    async def login(self) -> None:
        """Authenticate and obtain a JWT token."""
        salt = await self._get_salt()
        salted_hash = self._generate_salted_hash(self.password, salt)

        client = await self._client()
        resp = await client.post(
            LOGIN_URL,
            json={
                "emailOrUsername": self.email,
                "password": self.password,
                "hash": salted_hash,
                "mobileApp": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        # Token may come as "jwt" or "token" depending on API version
        self.token = data.get("jwt") or data.get("token")
        if not self.token:
            raise SchulmanagerAPIError(
                f"Login failed: no token received. Keys: {list(data.keys())}"
            )

        # Token valid for ~1h, refresh 5 min before expiry
        self.token_expiry = time.time() + 3300

        # Store institution ID from user data
        user = data.get("user", {})
        inst = user.get("institutionId")
        if inst is not None:
            self.institution_id = int(inst)

        # Extract student info from the user data
        self.students = []
        associated = user.get("associatedParents", [])
        if associated:
            for parent_link in associated:
                student = parent_link.get("student")
                if student:
                    self.students.append(student)
        else:
            # Direct student account
            assoc_student = user.get("associatedStudent")
            if assoc_student:
                self.students.append(assoc_student)

        # Try to get the current bundle version
        self.bundle_version = await self._fetch_bundle_version()

    async def ensure_authenticated(self) -> None:
        """Re-authenticate if token is expired or missing."""
        if not self.token or time.time() >= self.token_expiry:
            await self.login()

    # ── API Calls ───────────────────────────────────────────────────

    async def api_call(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Make a batch request to the /api/calls endpoint.

        Args:
            requests: List of request objects, each with moduleName,
                      endpointName, and parameters.

        Returns:
            List of result objects from the API (each has 'status' and 'data').
        """
        await self.ensure_authenticated()
        client = await self._client()

        payload = {
            "bundleVersion": self.bundle_version,
            "requests": requests,
        }

        resp = await client.post(
            CALLS_URL,
            json=payload,
            headers={"Authorization": f"Bearer {self.token}"},
        )

        if resp.status_code == 401:
            # Token expired, re-login and retry
            await self.login()
            resp = await client.post(
                CALLS_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
            )

        resp.raise_for_status()
        body = resp.json()

        # Response format: {"results": [...], "systemStatusMessages": [...]}
        if isinstance(body, dict):
            return body.get("results", [])
        return body

    async def single_call(
        self, module: str, endpoint: str, parameters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Convenience wrapper for a single API call.

        Returns the data from the first result in the batch response.
        """
        req = {
            "moduleName": module,
            "endpointName": endpoint,
            "parameters": parameters or {},
        }
        results = await self.api_call([req])
        if isinstance(results, list) and len(results) > 0:
            result = results[0]
            if isinstance(result, dict):
                if result.get("status") == "error":
                    raise SchulmanagerAPIError(
                        result.get("message", "Unknown API error")
                    )
                # Return the data payload directly
                return result.get("data", result)
            return result
        return {}

    # ── High-level Data Access ──────────────────────────────────────

    async def get_institution(self) -> dict[str, Any]:
        return await self.single_call("main", "get-institution")

    async def get_schedule(
        self, student_id: int, start: str, end: str
    ) -> dict[str, Any]:
        return await self.single_call(
            "schedules",
            "get-actual-lessons",
            {"student": {"id": student_id}, "start": start, "end": end},
        )

    async def get_homework(self, student_id: int) -> dict[str, Any]:
        return await self.single_call(
            "classbook",
            "get-homework",
            {"student": {"id": student_id}},
        )

    async def get_exams(
        self, student_id: int, start: str, end: str
    ) -> dict[str, Any]:
        return await self.single_call(
            "exams",
            "get-exams",
            {"student": {"id": student_id}, "start": start, "end": end},
        )

    async def get_grades(self, student_id: int) -> dict[str, Any]:
        return await self.single_call(
            "grades",
            "get-grades",
            {"student": {"id": student_id}},
        )

    async def get_letters(self) -> dict[str, Any]:
        return await self.single_call("letters", "get-letters")
