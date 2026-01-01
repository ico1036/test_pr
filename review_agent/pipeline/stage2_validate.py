"""Stage 2: Issue Validation - Validate issues with evidence from codebase."""

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

from ..models import PotentialIssue, ValidatedIssue
from ..tools import StorageTool


STAGE2_PROMPT = """
You are validating a potential code issue. Your job is to determine if this is a REAL issue or a FALSE POSITIVE.

## Available Tools
1. **serena** - Search the codebase for related code, usage patterns, and context
2. **context7** - Look up library documentation if the issue involves external libraries

## Potential Issue to Validate
- **File:** {file_path}
- **Lines:** {line_start}-{line_end}
- **Type:** {issue_type}
- **Severity:** {severity}
- **Description:** {description}
- **Code:**
```
{code_snippet}
```

## Validation Process
1. Use `serena` to search for:
   - How this pattern is used elsewhere in the codebase
   - Related code that might provide context
   - Similar implementations that might justify the pattern

2. Use `context7` if the issue involves:
   - External library usage
   - Framework-specific patterns
   - API documentation

3. Based on your findings, determine:
   - Is this a REAL issue that needs fixing?
   - Or is it a FALSE POSITIVE (acceptable pattern, intentional design)?

## Call store_verdict with:
- is_valid: true if this is a real issue, false if it's a false positive
- evidence: list of findings from your investigation (what you found in codebase/docs)
- library_reference: relevant documentation URL or quote (if applicable)
- mitigation: how to fix the issue (if it's valid)
- confidence: your confidence level from 0.0 to 1.0

Now investigate this issue and provide your verdict.
"""


_verdict_storage: StorageTool[dict] = StorageTool()


@tool(
    "store_verdict",
    "Store the validation verdict for an issue",
    {
        "is_valid": bool,
        "evidence": list,  # List[str]
        "library_reference": str,
        "mitigation": str,
        "confidence": float,
    }
)
async def store_verdict(args: dict[str, Any]) -> dict[str, Any]:
    """Store the validation verdict."""
    return _verdict_storage.store(args)


async def validate_single_issue(issue: PotentialIssue) -> ValidatedIssue:
    """
    Validate a single potential issue with evidence.

    Uses serena for codebase search and context7 for library docs.

    Args:
        issue: The potential issue to validate

    Returns:
        ValidatedIssue with evidence and verdict
    """
    print(f"  [Validate] {issue.file_path}:{issue.line_start} ({issue.severity})")

    global _verdict_storage
    _verdict_storage = StorageTool()

    # Create MCP server with verdict tool
    validate_server = create_sdk_mcp_server(
        name="review-stage2",
        version="1.0.0",
        tools=[store_verdict]
    )

    # Configure agent with serena and context7 MCP servers
    options = ClaudeAgentOptions(
        system_prompt="""You are a senior code reviewer validating potential issues.
Your goal is to determine if an issue is real or a false positive by gathering
evidence from the codebase and documentation. Be thorough but objective.""",

        mcp_servers={
            "validate": validate_server,
            # serena for codebase search
            "serena": {
                "type": "stdio",
                "command": "uvx",
                "args": [
                    "--from", "git+https://github.com/oraios/serena",
                    "serena", "start-mcp-server",
                    "--context", "ide-assistant"
                ]
            },
            # context7 for library documentation
            "context7": {
                "type": "sse",
                "url": "https://mcp.context7.com/mcp"
            }
        },

        allowed_tools=[
            "mcp__validate__store_verdict",
            # serena tools
            "mcp__serena__search_codebase",
            "mcp__serena__find_references",
            "mcp__serena__get_symbol_info",
            # context7 tools
            "mcp__context7__resolve-library-id",
            "mcp__context7__get-library-docs",
        ],

        permission_mode="acceptEdits",
        max_turns=20,
    )

    prompt = STAGE2_PROMPT.format(
        file_path=issue.file_path,
        line_start=issue.line_start,
        line_end=issue.line_end,
        issue_type=issue.issue_type,
        severity=issue.severity,
        description=issue.description,
        code_snippet=issue.code_snippet,
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text = block.text.strip()
                        if text and len(text) > 10:
                            preview = text[:80] + "..." if len(text) > 80 else text
                            print(f"    Investigating: {preview}")
                    elif isinstance(block, ToolUseBlock):
                        tool_name = block.name.split("__")[-1]
                        print(f"    Using tool: {tool_name}")

            elif isinstance(message, ResultMessage):
                duration_sec = message.duration_ms / 1000
                verdict = "valid" if _verdict_storage.values and _verdict_storage.values[0].get("is_valid") else "false positive"
                print(f"    Result: {verdict} ({duration_sec:.1f}s)")
                if message.is_error:
                    print(f"    Error: {message}")

    # Build ValidatedIssue from verdict
    if _verdict_storage.values:
        verdict = _verdict_storage.values[0]
        return ValidatedIssue(
            issue=issue,
            is_valid=verdict.get("is_valid", False),
            evidence=verdict.get("evidence", []),
            library_reference=verdict.get("library_reference"),
            mitigation=verdict.get("mitigation"),
            confidence=float(verdict.get("confidence", 0.0)),
        )
    else:
        # No verdict stored - assume inconclusive
        return ValidatedIssue(
            issue=issue,
            is_valid=False,
            evidence=["Validation inconclusive"],
            confidence=0.0,
        )


async def validate_issues(
    potential_issues: List[PotentialIssue],
    parallel: bool = False
) -> List[ValidatedIssue]:
    """
    Stage 2: Validate all potential issues with evidence.

    Uses serena for codebase search and context7 for library documentation.
    Strategy: High precision - filter false positives with evidence.

    Args:
        potential_issues: List of potential issues from Stage 1
        parallel: Whether to validate issues in parallel (uses more resources)

    Returns:
        List of ValidatedIssue objects
    """
    if not potential_issues:
        return []

    print(f"Stage 2: Validating {len(potential_issues)} potential issues...")
    print(f"  Mode: {'parallel' if parallel else 'sequential'}")

    if parallel:
        # Parallel validation (faster but more resource intensive)
        print(f"  Starting {len(potential_issues)} parallel validations...")
        tasks = [validate_single_issue(issue) for issue in potential_issues]
        validated = await asyncio.gather(*tasks, return_exceptions=True)
        print("  All parallel validations completed")

        # Filter out exceptions
        results = []
        for i, result in enumerate(validated):
            if isinstance(result, Exception):
                print(f"  Warning: Failed to validate issue {i}: {result}")
                # Create inconclusive result
                results.append(ValidatedIssue(
                    issue=potential_issues[i],
                    is_valid=False,
                    evidence=[f"Validation failed: {result}"],
                    confidence=0.0,
                ))
            else:
                results.append(result)
        return results
    else:
        # Sequential validation (more stable)
        validated = []
        for i, issue in enumerate(potential_issues):
            print(f"  [{i+1}/{len(potential_issues)}] Validating: {issue.file_path}:{issue.line_start}")
            try:
                result = await validate_single_issue(issue)
                validated.append(result)
            except Exception as e:
                print(f"    Warning: Failed - {e}")
                validated.append(ValidatedIssue(
                    issue=issue,
                    is_valid=False,
                    evidence=[f"Validation failed: {e}"],
                    confidence=0.0,
                ))
        return validated


# Synchronous wrapper
def validate_issues_sync(
    potential_issues: List[PotentialIssue],
    parallel: bool = False
) -> List[ValidatedIssue]:
    """Synchronous wrapper for validate_issues."""
    return asyncio.run(validate_issues(potential_issues, parallel))
