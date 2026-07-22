# GitHub App authentication

MEZO uses a GitHub App installation token rather than a broad permanent Personal Access Token. The private key remains in `mezo-api`; it is never stored in a workspace or sent to Kilo.

## App permissions

Configure the narrowest repository permissions that support Phase 1:

| Permission | Level | Purpose |
|---|---|---|
| Contents | Read and write | Clone, create a branch ref by push, and commit content |
| Pull requests | Read and write | Create and read Draft Pull Requests |
| Actions | Read | Optional validation/status inspection |
| Metadata | Read | GitHub-required repository metadata |

Do not grant administration, organization members, secrets, environments, deployments, repository deletion, visibility, branch-protection administration, or webhook write permissions. Install the App only on explicitly authorized repositories, beginning with `hypermezo4-create/DeadZone_xiaomi-Lite` and the MEZO repository if it will be operated by the product.

## Runtime flow

1. Owner authorizes a repository record and its App installation ID.
2. For clone, the API signs a GitHub App JWT (under ten minutes) and exchanges it for a short-lived token restricted to the task repository with contents read permission.
3. The runner uses that token through `GIT_ASKPASS`, with terminal prompting disabled.
4. After validation, MEZO stores the exact diff hash and commit SHA. No token is issued for push while approval is pending.
5. After approval and the separate publish action, the API issues another token restricted to that repository with contents write permission. Branch verification receives contents read; PR creation receives contents read and pull-requests write.
6. The runner performs one non-force push to the generated `mezo/task-…` branch.
7. The API reads GitHub’s branch ref and requires it to equal the approved SHA.
8. The API sends `draft: true` to GitHub’s Pull Request endpoint and persists the returned `html_url`.

There is no merge method. MEZO cannot force-push, delete a branch, alter protection, change visibility, or change organization permissions through its implementation.

## Configuration

Set `GITHUB_APP_ID`, default `GITHUB_INSTALLATION_ID`, and `GITHUB_APP_PRIVATE_KEY` as API secrets. A repository-specific installation ID in PostgreSQL overrides the default. `GITHUB_API_URL` defaults to `https://api.github.com` and can support a trusted GitHub Enterprise endpoint.

PEM parsing/signing errors, unreachable endpoints, HTTP failures, missing URL, invalid branch SHA, and commit mismatch fail explicitly. Error messages exclude response bodies so token-bearing or private provider details are not logged.

## Rotation

Create a second GitHub App private key, update the Fly secret, deploy/health-check, then delete the prior key in GitHub. Do not rotate during `creating_pull_request`. Rotation is an owner-controlled infrastructure action outside the Phase 1 API and requires an explicit operational change record.

## Validation checklist

- Installation is limited to selected repositories.
- App cannot merge or administer repositories.
- Clone succeeds without embedding a token in `.git/config` or process arguments.
- A task cannot obtain publish credentials before approval.
- Force-push is rejected locally.
- An altered GitHub branch SHA causes the task to fail and no PR to be created.
- A successful PR is visibly marked Draft and targets the intended base branch.
