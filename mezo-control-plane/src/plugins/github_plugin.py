"""
mezo-control-plane/src/plugins/github_plugin.py

GitHub integration for MEZO AI — real PyGithub-backed PR and issue actions.
ALL actions route through PermissionGuard.

Requires: GITHUB_TOKEN env var. Plugin is a no-op if token is absent.
"""

import os
from typing import Optional

from src.orchestrator.permission_guard import (
    PermissionGuard, PluginAction, Tier, ExecutionResult
)

# ---------------------------------------------------------------------------
# Action declarations
# ---------------------------------------------------------------------------

ACTION_GET_REPO = PluginAction(
    name="git.get_repo",
    description="Read repository metadata",
    tier=Tier.READ,
)
ACTION_LIST_PRS = PluginAction(
    name="git.list_prs",
    description="List open pull requests",
    tier=Tier.READ,
)
ACTION_GET_PR = PluginAction(
    name="git.get_pr",
    description="Read pull request details",
    tier=Tier.READ,
)
ACTION_LIST_ISSUES = PluginAction(
    name="git.list_issues",
    description="List open issues",
    tier=Tier.READ,
)
ACTION_CREATE_DRAFT_PR = PluginAction(
    name="git.create_draft_pr",
    description="Create a draft pull request",
    tier=Tier.REVERSIBLE_WRITE,
    target_description="Opens a draft PR (can be closed/deleted, not merged yet)",
)
ACTION_ADD_PR_COMMENT = PluginAction(
    name="git.add_pr_comment",
    description="Add a comment to a pull request",
    tier=Tier.REVERSIBLE_WRITE,
    target_description="Adds a comment to the specified PR",
)
ACTION_MERGE_PR = PluginAction(
    name="git.merge_pr",
    description="Merge a pull request",
    tier=Tier.IRREVERSIBLE,
    target_description="Merges the PR into the target branch — cannot be undone without a revert commit",
)
ACTION_CLOSE_PR = PluginAction(
    name="git.close_pr",
    description="Close a pull request without merging",
    tier=Tier.REVERSIBLE_WRITE,
    target_description="Closes the PR (can be re-opened)",
)


class GitHubPlugin:
    """
    Real GitHub actions via PyGithub.

    All methods accept (guard, actor_user_id, session_id, ...) and return ExecutionResult.
    """

    def __init__(self, guard: PermissionGuard, token: Optional[str] = None):
        self._guard = guard
        self._token = token or os.environ.get("GITHUB_TOKEN", "")
        self._gh = None  # lazy-initialized

    def _get_gh(self):
        """Lazy-load PyGithub to avoid import error when token is absent."""
        if self._gh is None:
            if not self._token:
                raise RuntimeError(
                    "GITHUB_TOKEN not set. GitHub plugin is unavailable. "
                    "Set GITHUB_TOKEN in your .env file."
                )
            try:
                from github import Github
            except ImportError:
                raise RuntimeError(
                    "PyGithub not installed. Run: pip install PyGithub"
                )
            self._gh = Github(self._token)
        return self._gh

    async def get_repo_info(
        self, repo_full_name: str, actor_user_id: str, session_id: str = ""
    ) -> ExecutionResult:
        async def _exec():
            import asyncio
            gh = self._get_gh()
            repo = await asyncio.to_thread(gh.get_repo, repo_full_name)
            return {
                "name": repo.full_name,
                "description": repo.description,
                "default_branch": repo.default_branch,
                "open_issues": repo.open_issues_count,
                "stars": repo.stargazers_count,
                "private": repo.private,
                "url": repo.html_url,
            }

        return await self._guard.execute_if_permitted(
            action=ACTION_GET_REPO, actor_user_id=actor_user_id,
            target=repo_full_name, executor=_exec, session_id=session_id,
        )

    async def list_pull_requests(
        self, repo_full_name: str, actor_user_id: str, session_id: str = "", state: str = "open"
    ) -> ExecutionResult:
        async def _exec():
            import asyncio
            gh = self._get_gh()
            repo = await asyncio.to_thread(gh.get_repo, repo_full_name)
            prs = await asyncio.to_thread(repo.get_pulls, state=state)
            return {
                "repo": repo_full_name,
                "prs": [
                    {
                        "number": pr.number,
                        "title": pr.title,
                        "state": pr.state,
                        "draft": pr.draft,
                        "user": pr.user.login,
                        "head": pr.head.ref,
                        "base": pr.base.ref,
                        "url": pr.html_url,
                    }
                    for pr in prs
                ],
            }

        return await self._guard.execute_if_permitted(
            action=ACTION_LIST_PRS, actor_user_id=actor_user_id,
            target=repo_full_name, executor=_exec, session_id=session_id,
        )

    async def create_draft_pr(
        self,
        repo_full_name: str,
        title: str,
        body: str,
        head: str,
        base: str,
        actor_user_id: str,
        session_id: str = "",
    ) -> ExecutionResult:
        async def _exec():
            import asyncio
            gh = self._get_gh()
            repo = await asyncio.to_thread(gh.get_repo, repo_full_name)
            pr = await asyncio.to_thread(
                repo.create_pull,
                title=title,
                body=body,
                head=head,
                base=base,
                draft=True,
            )
            return {
                "number": pr.number,
                "title": pr.title,
                "draft": pr.draft,
                "url": pr.html_url,
                "head": head,
                "base": base,
            }

        return await self._guard.execute_if_permitted(
            action=ACTION_CREATE_DRAFT_PR, actor_user_id=actor_user_id,
            target=f"{repo_full_name} [{head} -> {base}]", executor=_exec, session_id=session_id,
        )

    async def merge_pr(
        self,
        repo_full_name: str,
        pr_number: int,
        actor_user_id: str,
        confirm_callback,
        session_id: str = "",
        task_id: Optional[str] = None,
        merge_method: str = "squash",
    ) -> ExecutionResult:
        """Tier.IRREVERSIBLE — always requires confirmation."""
        async def _exec():
            import asyncio
            gh = self._get_gh()
            repo = await asyncio.to_thread(gh.get_repo, repo_full_name)
            pr = await asyncio.to_thread(repo.get_pull, pr_number)
            result = await asyncio.to_thread(pr.merge, merge_method=merge_method)
            return {
                "merged": result.merged,
                "message": result.message,
                "sha": result.sha,
                "pr_number": pr_number,
                "repo": repo_full_name,
            }

        return await self._guard.execute_if_permitted(
            action=ACTION_MERGE_PR, actor_user_id=actor_user_id,
            target=f"{repo_full_name}#{pr_number}", executor=_exec,
            confirm_callback=confirm_callback, session_id=session_id, task_id=task_id,
        )
