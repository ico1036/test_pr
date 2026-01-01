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

      - name: Install review-agent
        run: uv pip install review-agent

      - name: Run AI PR Review
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          uv run review-agent \\
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

    # Create workflow
    workflow_dir = target / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)

    workflow_file = workflow_dir / "pr-review.yml"
    if workflow_file.exists():
        print(f"Warning: {workflow_file} already exists, skipping")
    else:
        workflow_file.write_text(WORKFLOW_TEMPLATE)
        print(f"Created {workflow_file}")

    # Create MCP config
    mcp_file = target / ".mcp.json"
    if mcp_file.exists():
        print(f"Warning: {mcp_file} already exists, skipping")
    else:
        mcp_file.write_text(MCP_CONFIG)
        print(f"Created {mcp_file}")

    print("\nSetup complete!")
    print("\nNext steps:")
    print("  1. Configure self-hosted runner (for Claude Code Max)")
    print("     Or add ANTHROPIC_API_KEY to GitHub secrets")
    print("  2. git add . && git commit -m 'Add AI PR Review'")
    print("  3. git push")

    return True


if __name__ == "__main__":
    init_repository()
