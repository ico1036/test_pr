"""Stage 3: Test Generation - Generate tests for PR changes."""

import asyncio
from typing import List, Any, Optional
from pathlib import Path

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

from ..models import (
    ValidatedIssue,
    GeneratedTest,
    TestType,
    TestCategory,
    TestGenConfig,
)
from ..tools import StorageTool


STAGE3_PROMPT = """
You are a TDD expert. Generate comprehensive test cases for the code changes in this PR.

## Your Mission
Create tests that verify the behavior of changed code from the **client's perspective**.
Focus on what users expect, not implementation details.

## Rules
1. **For each changed function/method**, generate:
   - Happy path test (normal successful execution)
   - Edge case tests (boundary values, empty, null, special characters)
   - Error case tests (exception handling, invalid inputs)

2. **Follow existing test patterns**:
   - Search the codebase for existing test files using serena
   - Match the naming conventions, structure, and style
   - Use the same test framework and assertions

3. **For each validated issue**, create a regression test:
   - The test should fail if the issue is present
   - The test should pass when the issue is fixed

4. **Test naming**: `test_<what>_<condition>_<expected>`
   - Example: `test_login_with_invalid_password_returns_error`

## PR Changes
{pr_diff}

## Validated Issues (create regression tests for these)
{validated_issues}

## Existing Test Patterns
Use serena to search for existing test files and patterns.
Look at: test naming, fixtures, mocking patterns, assertion styles.

## Instructions
1. First, use serena to find existing test files and understand patterns
2. For each changed function, call `store_test` to save generated test code
3. Include all test categories: happy_path, edge_case, error_case, regression
4. Ensure tests are self-contained and can run independently

Call `store_test` for each test file you generate.
"""


# Define the store_test tool
_test_storage: StorageTool[dict] = StorageTool()


@tool(
    "store_test",
    "Store a generated test file",
    {
        "file_path": str,          # e.g., tests/test_feature.py
        "content": str,            # Full test file content
        "covers_functions": list,  # List of function names covered
        "covers_issues": list,     # List of issue IDs covered (optional)
        "test_type": str,          # unit, integration, e2e
        "categories": list,        # happy_path, edge_case, error_case, regression
    }
)
async def store_test(args: dict[str, Any]) -> dict[str, Any]:
    """Store a generated test file."""
    return _test_storage.store(args)


async def generate_tests(
    pr_diff: str,
    validated_issues: List[ValidatedIssue],
    config: Optional[TestGenConfig] = None,
) -> List[GeneratedTest]:
    """
    Stage 3: Generate tests for PR changes.

    Uses Claude Agent SDK with serena MCP to understand codebase patterns.

    Args:
        pr_diff: The PR diff text
        validated_issues: Issues found in Stage 1,2 (for regression tests)
        config: Test generation configuration

    Returns:
        List of GeneratedTest objects
    """
    global _test_storage
    _test_storage = StorageTool()
    config = config or TestGenConfig()

    # Format validated issues for prompt
    issues_text = _format_issues(validated_issues)

    # Create MCP server with our tool
    test_server = create_sdk_mcp_server(
        name="test-gen",
        version="1.0.0",
        tools=[store_test]
    )

    # Configure agent options
    options = ClaudeAgentOptions(
        system_prompt=f"""You are a TDD expert specialized in writing comprehensive tests.
Follow the {config.test_framework} testing framework conventions.
Generate tests that verify behavior from the client's perspective.""",

        mcp_servers={
            "testgen": test_server,
            # serena for codebase search
            "serena": {
                "type": "stdio",
                "command": "uvx",
                "args": ["serena", "--workspace", "."]
            },
            # context7 for library documentation
            "context7": {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@context7/mcp"]
            }
        },

        allowed_tools=[
            "mcp__testgen__store_test",
            "mcp__serena__search_codebase",
            "mcp__serena__read_file",
            "mcp__serena__find_definition",
            "mcp__context7__lookup",
        ],

        permission_mode="acceptEdits",
        max_turns=50,  # More turns for test generation
    )

    # Run agent
    print("  [Stage 3] Starting test generation...")
    test_count = 0

    async with ClaudeSDKClient(options=options) as client:
        await client.query(STAGE3_PROMPT.format(
            pr_diff=pr_diff,
            validated_issues=issues_text
        ))

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text = block.text.strip()
                        if text and len(text) > 10:
                            preview = text[:100] + "..." if len(text) > 100 else text
                            print(f"  [Stage 3] {preview}")
                    elif isinstance(block, ToolUseBlock):
                        if block.name == "mcp__testgen__store_test":
                            test_count += 1
                            file_path = block.input.get("file_path", "unknown")
                            print(f"  [Stage 3] Generated test #{test_count}: {file_path}")

            elif isinstance(message, ResultMessage):
                duration_sec = message.duration_ms / 1000
                print(f"  [Stage 3] Completed in {duration_sec:.1f}s - Generated {test_count} test files")
                if message.is_error:
                    print(f"  [Stage 3] Error: {message}")

    # Convert stored dicts to GeneratedTest objects
    tests = []
    for data in _test_storage.values:
        try:
            # Parse test type
            test_type_str = data.get("test_type", "unit").lower()
            test_type = TestType.UNIT
            if test_type_str == "integration":
                test_type = TestType.INTEGRATION
            elif test_type_str == "e2e":
                test_type = TestType.E2E

            # Parse categories
            categories = []
            for cat in data.get("categories", []):
                cat_lower = cat.lower().replace("-", "_")
                if cat_lower == "happy_path":
                    categories.append(TestCategory.HAPPY_PATH)
                elif cat_lower == "edge_case":
                    categories.append(TestCategory.EDGE_CASE)
                elif cat_lower == "error_case":
                    categories.append(TestCategory.ERROR_CASE)
                elif cat_lower == "regression":
                    categories.append(TestCategory.REGRESSION)

            test = GeneratedTest(
                file_path=data.get("file_path", ""),
                content=data.get("content", ""),
                covers_functions=data.get("covers_functions", []),
                covers_issues=data.get("covers_issues", []),
                test_type=test_type,
                categories=categories,
            )
            tests.append(test)
        except (ValueError, TypeError) as e:
            print(f"Warning: Failed to parse test: {e}")

    return tests


def _format_issues(issues: List[ValidatedIssue]) -> str:
    """Format validated issues for the prompt."""
    if not issues:
        return "No validated issues found."

    lines = []
    for i, issue in enumerate(issues, 1):
        if issue.is_valid:
            lines.append(f"""
Issue #{i}:
- File: {issue.issue.file_path}
- Lines: {issue.issue.line_start}-{issue.issue.line_end}
- Type: {issue.issue.issue_type}
- Severity: {issue.issue.severity}
- Description: {issue.issue.description}
- Mitigation: {issue.mitigation or 'N/A'}
""")

    return "\n".join(lines) if lines else "No valid issues to create regression tests for."


# Synchronous wrapper
def generate_tests_sync(
    pr_diff: str,
    validated_issues: List[ValidatedIssue],
    config: Optional[TestGenConfig] = None,
) -> List[GeneratedTest]:
    """Synchronous wrapper for generate_tests."""
    return asyncio.run(generate_tests(pr_diff, validated_issues, config))
