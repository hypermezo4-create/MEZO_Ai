from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
import jwt

from src.config import get_settings


class GitHubAppError(RuntimeError):
    pass


class GitHubAppClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def configured(self) -> bool:
        return bool(
            self.settings.github_app_id
            and self.settings.github_installation_id
            and self.settings.github_private_key
        )

    def _app_jwt(self) -> str:
        if not self.configured():
            raise GitHubAppError("GitHub App credentials are not configured")
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {"iat": now - timedelta(seconds=30), "exp": now + timedelta(minutes=9), "iss": self.settings.github_app_id},
            self.settings.github_private_key,
            algorithm="RS256",
        )

    async def installation_token(
        self,
        installation_id: str | None,
        *,
        repository: str,
        permissions: dict[str, str],
    ) -> tuple[str, datetime]:
        resolved_installation = installation_id or self.settings.github_installation_id
        if not resolved_installation:
            raise GitHubAppError("Repository GitHub App installation is not configured")
        try:
            app_token = self._app_jwt()
        except (ValueError, TypeError, jwt.PyJWTError) as exc:
            raise GitHubAppError("GitHub App private key could not sign an authentication token") from exc
        headers = {
            "Authorization": f"Bearer {app_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        url = f"{self.settings.github_api_url}/app/installations/{resolved_installation}/access_tokens"
        repository_name = repository.split("/", 1)[1]
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json={"repositories": [repository_name], "permissions": permissions},
                )
        except httpx.RequestError as exc:
            raise GitHubAppError("GitHub installation token endpoint is unreachable") from exc
        if response.status_code >= 400:
            raise GitHubAppError(f"GitHub installation token request failed with HTTP {response.status_code}")
        payload = response.json()
        return payload["token"], datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))

    async def create_draft_pull_request(
        self,
        *,
        repository: str,
        head: str,
        base: str,
        title: str,
        body: str,
        installation_id: str | None,
    ) -> str:
        token, _ = await self.installation_token(
            installation_id,
            repository=repository,
            permissions={"contents": "read", "pull_requests": "write"},
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.settings.github_api_url}/repos/{repository}/pulls",
                    headers=headers,
                    json={"title": title, "body": body, "head": head, "base": base, "draft": True},
                )
        except httpx.RequestError as exc:
            raise GitHubAppError("GitHub Pull Request endpoint is unreachable") from exc
        if response.status_code != 201:
            raise GitHubAppError(f"GitHub Draft Pull Request creation failed with HTTP {response.status_code}")
        url = response.json().get("html_url")
        if not url:
            raise GitHubAppError("GitHub response did not include a Pull Request URL")
        return url

    async def branch_sha(
        self,
        *,
        repository: str,
        branch: str,
        installation_id: str | None,
    ) -> str:
        token, _ = await self.installation_token(
            installation_id,
            repository=repository,
            permissions={"contents": "read"},
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    f"{self.settings.github_api_url}/repos/{repository}/git/ref/heads/{quote(branch, safe='')}",
                    headers=headers,
                )
        except httpx.RequestError as exc:
            raise GitHubAppError("GitHub branch verification endpoint is unreachable") from exc
        if response.status_code != 200:
            raise GitHubAppError(f"GitHub branch verification failed with HTTP {response.status_code}")
        sha = response.json().get("object", {}).get("sha")
        if not isinstance(sha, str) or len(sha) != 40:
            raise GitHubAppError("GitHub branch verification returned an invalid commit SHA")
        return sha
