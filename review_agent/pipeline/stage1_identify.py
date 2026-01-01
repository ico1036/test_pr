"""Stage 1: Issue Identification - Find all potential issues in code changes."""

import asyncio
from typing import List, Any

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    tool,
    create_sdk_mcp_server,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ResultMessage,
)

from ..models import PotentialIssue
from ..tools import StorageTool


STAGE1_PROMPT = """
You are an expert code reviewer. Analyze the following code changes (hunks) and identify ALL potential issues.

## Your Mission
Be aggressive in finding issues - it's okay to have false positives at this stage.
They will be filtered in the next stage through evidence-based validation.

## Categories to Look For
1. **Bugs and Logic Errors** - Off-by-one errors, null pointer issues, incorrect conditions
2. **Security Vulnerabilities** - XSS, SQL injection, command injection, path traversal
3. **Performance Issues** - N+1 queries, unnecessary loops, memory leaks
4. **Type Errors** - Type mismatches, incorrect type assertions
5. **Unused Code** - Dead code, unused variables, unreachable code
6. **Best Practice Violations** - Anti-patterns, code smells, maintainability issues

## For Each Issue Found
Call the `store_issue` tool with:
- file_path: path to the file
- line_start: starting line number
- line_end: ending line number
- issue_type: one of [bug, security, performance, logic_error, type_error, unused_code, best_practice]
- severity: one of [critical, high, medium, low]
- description: clear explanation of what the issue is and why it matters
- code_snippet: the problematic code

## Severity Guidelines
- **critical**: Security vulnerabilities, data loss risks, crashes
- **high**: Bugs that affect functionality, serious performance issues
- **medium**: Code quality issues, minor bugs, maintainability concerns
- **low**: Style issues, minor improvements, suggestions

## Code Changes to Analyze
{hunks}

Now analyze the code and identify all potential issues. Call store_issue for each one found.
"""


# Define the store_issue tool
_issue_storage: StorageTool[dict] = StorageTool()


@tool(
    "store_issue",
    "Store a potential issue found in the code review",
    {
        "file_path": str,
        "line_start": int,
        "line_end": int,
        "issue_type": str,
        "severity": str,
        "description": str,
        "code_snippet": str,
    }
)
async def store_issue(args: dict[str, Any]) -> dict[str, Any]:
    """Store a potential issue found during code review."""
    return _issue_storage.store(args)


async def identify_issues(hunks_text: str) -> List[PotentialIssue]:
    """
    Stage 1: Identify all potential issues in code changes.

    Uses Claude Agent SDK with sequential-thinking MCP for complex reasoning.
    Strategy: High recall - find all possible issues (false positives OK)

    Args:
        hunks_text: Formatted string of code changes

    Returns:
        List of PotentialIssue objects
    """
    global _issue_storage
    _issue_storage = StorageTool()

    # Create MCP server with our tool
    review_server = create_sdk_mcp_server(
        name="review-stage1",
        version="1.0.0",
        tools=[store_issue]
    )

    # Configure agent options
    options = ClaudeAgentOptions(
        system_prompt="""You are an expert code reviewer specialized in finding bugs,
security vulnerabilities, and code quality issues. Be thorough and identify all
potential problems - false positives will be filtered in the next stage.""",

        mcp_servers={
            "review": review_server,
            # sequential-thinking for complex reasoning
            "thinking": {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
            }
        },

        allowed_tools=[
            "mcp__review__store_issue",
            "mcp__thinking__sequentialthinking",
        ],

        permission_mode="acceptEdits",
        max_turns=30,
    )

    # Run agent
    async with ClaudeSDKClient(options=options) as client:
        await client.query(STAGE1_PROMPT.format(hunks=hunks_text))

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        # Log assistant thinking
                        pass
                    elif isinstance(block, ToolUseBlock):
                        # Tool calls are handled automatically
                        pass

            elif isinstance(message, ResultMessage):
                # Agent completed
                print(f"Stage 1 completed in {message.duration_ms}ms")
                if message.is_error:
                    print(f"Error: {message}")

    # Convert stored dicts to PotentialIssue objects
    issues = []
    for data in _issue_storage.values:
        try:
            issue = PotentialIssue(
                file_path=data.get("file_path", ""),
                line_start=int(data.get("line_start", 0)),
                line_end=int(data.get("line_end", 0)),
                issue_type=data.get("issue_type", "bug"),
                severity=data.get("severity", "medium"),
                description=data.get("description", ""),
                code_snippet=data.get("code_snippet", ""),
            )
            issues.append(issue)
        except (ValueError, TypeError) as e:
            print(f"Warning: Failed to parse issue: {e}")

    return issues


# Synchronous wrapper for non-async contexts
def identify_issues_sync(hunks_text: str) -> List[PotentialIssue]:
    """Synchronous wrapper for identify_issues."""
    return asyncio.run(identify_issues(hunks_text))
