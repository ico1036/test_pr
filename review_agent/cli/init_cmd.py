"""Initialize review-agent in a repository."""

import shutil
from pathlib import Path


WORKFLOW_TEMPLATE = '''name: AI PR Review

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    name: AI Code Review
    runs-on: self-hosted

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync

      - name: Run AI PR Review
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          uv run review-agent review \\
            --repo "${{ github.repository }}" \\
            --pr-number "${{ github.event.pull_request.number }}"
'''

MCP_CONFIG = '''{
  "mcpServers": {
    "server-sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    },
    "context7": {
      "url": "https://mcp.context7.com/mcp"
    },
    "serena": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/oraios/serena",
        "serena", "start-mcp-server",
        "--context", "ide-assistant"
      ]
    }
  }
}
'''


def init_repository(target_dir: Path = None):
    """
    Initialize review-agent in a repository.

    Creates:
      - .github/workflows/pr-review.yml
      - .mcp.json
    """
    target = target_dir or Path.cwd()

    # Check if git repo
    if not (target / ".git").exists():
        print(f"Error: {target} is not a git repository")
        return False

    created_files = []

    # Create workflow
    workflow_dir = target / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)

    workflow_file = workflow_dir / "pr-review.yml"
    if workflow_file.exists():
        print(f"Already exists: {workflow_file}")
    else:
        workflow_file.write_text(WORKFLOW_TEMPLATE)
        print(f"Created: {workflow_file}")
        created_files.append(workflow_file)

    # Create MCP config
    mcp_file = target / ".mcp.json"
    if mcp_file.exists():
        print(f"Already exists: {mcp_file}")
    else:
        mcp_file.write_text(MCP_CONFIG)
        print(f"Created: {mcp_file}")
        created_files.append(mcp_file)

    if created_files:
        print("\nNext steps:")
        print("  1. git add . && git commit -m 'Add AI PR Review'")
        print("  2. git push")
        print("  3. Configure self-hosted runner (Settings → Actions → Runners)")
    else:
        print("\nAlready configured. No changes needed.")

    return True


if __name__ == "__main__":
    init_repository()
