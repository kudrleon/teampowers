#!/usr/bin/env bash
# Detect provider, branch, PR number for the current repo.
#
# stdout: JSON object (see spec §5.3 step 1).
# stderr: structured JSON on failure (see references/errors.md).
# exit:   0 on success, non-zero on failure.
#
# Test seam:
#   TEAMPOWERS_TEST=1            — skip live az/gh calls
#   TEAMPOWERS_FAKE_PR="1234"    — pretend the lookup returned this PR
#   TEAMPOWERS_FAKE_PR=""        — pretend no PR exists
set -euo pipefail

fail() {
  local code="$1" message="$2" fix="${3:-null}"
  if [[ "$fix" != "null" ]]; then fix="\"$fix\""; fi
  printf '{"error":"%s","message":"%s","fix":%s}\n' \
    "$code" "$message" "$fix" >&2
  exit 1
}

remote_url=$(git config --get remote.origin.url 2>/dev/null || true)
if [[ -z "$remote_url" ]]; then
  fail "unsupported_provider" "no remote.origin.url configured" \
    "Add a git remote pointing to GitHub or Azure DevOps."
fi

# Strip a trailing .git so downstream regexes don't have to handle it.
# (POSIX ERE used by bash =~ does not support non-greedy quantifiers like
# +? or *?; macOS bash 3.2 in particular silently mismatches them. Strip
# up front and the patterns can use plain `[^/]+`.)
remote_url="${remote_url%.git}"

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)

provider=""
org=""
project=""
repo=""

# --- Azure DevOps ---
# https://dev.azure.com/<org>/<project>/_git/<repo>
# git@ssh.dev.azure.com:v3/<org>/<project>/<repo>
if [[ "$remote_url" =~ ^https://dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/]+)$ ]]; then
  provider="azdo"
  org="${BASH_REMATCH[1]}"
  project="${BASH_REMATCH[2]}"
  repo="${BASH_REMATCH[3]}"
elif [[ "$remote_url" =~ ^git@ssh\.dev\.azure\.com:v3/([^/]+)/([^/]+)/([^/]+)$ ]]; then
  provider="azdo"
  org="${BASH_REMATCH[1]}"
  project="${BASH_REMATCH[2]}"
  repo="${BASH_REMATCH[3]}"
# --- GitHub ---
# https://github.com/<owner>/<repo>
# git@github.com:<owner>/<repo>
# (trailing .git was stripped above)
elif [[ "$remote_url" =~ ^https://github\.com/([^/]+/[^/]+)$ ]]; then
  provider="github"
  repo="${BASH_REMATCH[1]}"
elif [[ "$remote_url" =~ ^git@github\.com:([^/]+/[^/]+)$ ]]; then
  provider="github"
  repo="${BASH_REMATCH[1]}"
else
  fail "unsupported_provider" \
    "remote URL not recognized: $remote_url" \
    "Supported: GitHub, Azure DevOps. See references/adding-providers.md."
fi

# --- PR lookup ---
pr_number=""
pr_url=""

if [[ "${TEAMPOWERS_TEST:-}" == "1" ]]; then
  pr_number="${TEAMPOWERS_FAKE_PR-}"
  if [[ -n "$pr_number" ]]; then
    if [[ "$provider" == "github" ]]; then
      pr_url="https://github.com/$repo/pull/$pr_number"
    else
      pr_url="https://dev.azure.com/$org/$project/_git/$repo/pullrequest/$pr_number"
    fi
  fi
elif [[ "$provider" == "github" ]]; then
  if ! command -v gh >/dev/null 2>&1; then
    fail "github_not_authed" "gh CLI is not installed" \
      "Install gh from https://cli.github.com/, then run gh auth login."
  fi
  # `gh pr view --json number,url` errors if no PR exists for the branch.
  if pr_json=$(gh pr view --json number,url 2>/dev/null); then
    pr_number=$(printf '%s' "$pr_json" | python3 -c 'import json,sys;print(json.load(sys.stdin)["number"])')
    pr_url=$(printf '%s'    "$pr_json" | python3 -c 'import json,sys;print(json.load(sys.stdin)["url"])')
  fi
elif [[ "$provider" == "azdo" ]]; then
  if ! command -v az >/dev/null 2>&1; then
    fail "azdo_not_logged_in" "az CLI is not installed" \
      "Install az CLI and run az login."
  fi
  # az repos pr list --status active --source-branch <branch> --org ... --project ... --repository ...
  if pr_json=$(az repos pr list \
        --status active \
        --source-branch "$branch" \
        --org   "https://dev.azure.com/$org" \
        --project "$project" \
        --repository "$repo" \
        --output json 2>/dev/null); then
    count=$(printf '%s' "$pr_json" | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))')
    if [[ "$count" == "1" ]]; then
      pr_number=$(printf '%s' "$pr_json" | python3 -c 'import json,sys;print(json.load(sys.stdin)[0]["pullRequestId"])')
      pr_url="https://dev.azure.com/$org/$project/_git/$repo/pullrequest/$pr_number"
    elif [[ "$count" -gt 1 ]]; then
      multiple=$(printf '%s' "$pr_json" | python3 -c '
import json,sys
prs=json.load(sys.stdin)
print(json.dumps([{"id":p["pullRequestId"],"title":p.get("title","")} for p in prs]))')
      jq_safe=$(printf '%s' "$multiple" | python3 -c 'import json,sys;print(json.dumps(json.load(sys.stdin)))')
      printf '{"provider":"%s","branch":"%s","org":"%s","project":"%s","repo":"%s","pr_number":null,"pr_url":null,"multiple_prs":%s}\n' \
        "$provider" "$branch" "$org" "$project" "$repo" "$jq_safe"
      exit 0
    fi
  fi
fi

if [[ -z "$pr_number" ]]; then
  fail "no_pr_for_branch" "no active PR found for branch $branch" \
    "Open a PR for this branch on the provider, then re-run."
fi

# --- emit JSON ---
if [[ "$provider" == "github" ]]; then
  printf '{"provider":"github","branch":"%s","repo":"%s","pr_number":"%s","pr_url":"%s","multiple_prs":null}\n' \
    "$branch" "$repo" "$pr_number" "$pr_url"
else
  printf '{"provider":"azdo","branch":"%s","org":"%s","project":"%s","repo":"%s","pr_number":"%s","pr_url":"%s","multiple_prs":null}\n' \
    "$branch" "$org" "$project" "$repo" "$pr_number" "$pr_url"
fi
