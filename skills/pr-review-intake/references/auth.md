# Authentication

This plugin never asks for credentials interactively and never writes
them to disk. It inherits whatever the provider's CLI already has.

## Azure DevOps

| Mechanism | When | How |
|---|---|---|
| `az login` (Entra ID) | Default for interactive workstations. | Scripts call `az rest`, which inherits the cached session. `detect_context.sh` runs `az` early to surface failures. |
| `AZURE_DEVOPS_EXT_PAT` env var | Headless CI, or when `az login` failed. | Scripts detect `az` failure and fall through to direct HTTP with HTTP Basic auth: `("", $PAT)`. |

**PAT scopes required:**
- `Code (read)` — for `pr-review-intake`.
- `Pull Request Threads (read & write)` — for `pr-review-update`.

**API version pin:** all AzDO REST calls pin `api-version=7.1`. Bumps are
deliberate code changes, not silent.

## GitHub

| Mechanism | When | How |
|---|---|---|
| `gh` CLI auth | Default. | Fetcher shells out to `gh api graphql`. |
| `GH_TOKEN` env var | Headless CI, or fallback. | `gh` itself respects `GH_TOKEN` — no extra plugin code needed. |

**PAT scopes required:**
- `repo` (or `public_repo` for public-only).

## Failure handling

Every script emits structured JSON on stderr if auth is missing or
invalid:

```json
{
  "error": "azdo_not_logged_in",
  "message": "az rest failed and AZURE_DEVOPS_EXT_PAT is not set",
  "fix": "Run: az login --use-device-code, OR export AZURE_DEVOPS_EXT_PAT=<your-pat>"
}
```

The SKILL.md instructs the agent to parse this and surface `fix` to the
user verbatim. There is no silent recovery and no retry chain.
