# PRD: AI PR Review Agent

## 1. Overview

### 1.1 Problem Statement
코드 리뷰는 시간이 많이 소요되며, 리뷰어의 피로도와 일관성 부족 문제가 있다. 자동화된 AI 리뷰 에이전트가 필요하다.

### 1.2 Solution
Claude Code Max 구독 + Claude Agent SDK를 활용한 2-Stage PR Review Agent 구축.
외부 API Key 없이 기존 구독만으로 운영.

### 1.3 Reference
- [Hyperithm Review Agent](https://tech.hyperithm.com/review-agent)

---

## 2. Architecture

### 2.1 High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           GitHub Repository                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   PR Created/Updated                                                     │
│         │                                                                │
│         ▼                                                                │
│   ┌──────────────┐                                                      │
│   │GitHub Actions│ ─── Self-hosted Runner (Claude Code 인증 유지)       │
│   └──────────────┘                                                      │
│         │                                                                │
│         ▼                                                                │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │                    Review Agent (Python)                          │  │
│   │                                                                   │  │
│   │   ┌─────────────────────────────────────────────────────────┐    │  │
│   │   │              Claude Agent SDK                            │    │  │
│   │   │   Backend: Claude Code CLI (Max 구독 인증)               │    │  │
│   │   │   Model: Claude Sonnet 4.5                               │    │  │
│   │   └─────────────────────────────────────────────────────────┘    │  │
│   │                          │                                        │  │
│   │                          ▼                                        │  │
│   │   ┌─────────────────────────────────────────────────────────┐    │  │
│   │   │                  MCP Servers                             │    │  │
│   │   │                                                          │    │  │
│   │   │  ┌──────────┐  ┌──────────┐  ┌────────────────────┐    │    │  │
│   │   │  │  serena  │  │ context7 │  │sequential-thinking │    │    │  │
│   │   │  │코드검색  │  │문서검색  │  │    복잡한 추론     │    │    │  │
│   │   │  └──────────┘  └──────────┘  └────────────────────┘    │    │  │
│   │   └─────────────────────────────────────────────────────────┘    │  │
│   │                          │                                        │  │
│   └──────────────────────────┼───────────────────────────────────────┘  │
│                              ▼                                           │
│                    ┌─────────────────┐                                  │
│                    │  GitHub PR API  │                                  │
│                    │  Review Comment │                                  │
│                    └─────────────────┘                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Two-Stage Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        2-Stage Review Pipeline                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ STAGE 1: Issue Identification (Recall 우선)                        │ │
│  │                                                                     │ │
│  │   Input: Git Diff Hunks                                            │ │
│  │                                                                     │ │
│  │   ┌─────────┐    ┌─────────────────┐    ┌──────────────────┐      │ │
│  │   │  Hunks  │ ─▶ │ LLM Analysis    │ ─▶ │ Potential Issues │      │ │
│  │   │ Parser  │    │ (적극적 발굴)   │    │ List (N개)       │      │ │
│  │   └─────────┘    └─────────────────┘    └──────────────────┘      │ │
│  │                                                                     │ │
│  │   Tools: sequential-thinking                                        │ │
│  │   Strategy: 가능한 모든 이슈 도출 (오탐 허용)                       │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                              │                                           │
│                              ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ STAGE 2: Issue Validation (Precision 우선)                         │ │
│  │                                                                     │ │
│  │   For each potential issue:                                         │ │
│  │                                                                     │ │
│  │   ┌──────────────┐    ┌───────────────┐    ┌──────────────────┐   │ │
│  │   │ serena       │    │ context7      │    │ Evidence         │   │ │
│  │   │ 코드베이스   │ ─▶ │ 라이브러리    │ ─▶ │ Collection       │   │ │
│  │   │ 검색         │    │ 문서 검색     │    │                  │   │ │
│  │   └──────────────┘    └───────────────┘    └──────────────────┘   │ │
│  │                                                    │               │ │
│  │                                                    ▼               │ │
│  │                              ┌─────────────────────────────────┐   │ │
│  │                              │ Verdict: Valid / False Positive │   │ │
│  │                              │ + Evidence + Mitigation         │   │ │
│  │                              └─────────────────────────────────┘   │ │
│  │                                                                     │ │
│  │   Tools: serena, context7                                           │ │
│  │   Strategy: 근거 기반 검증, 오탐 제거                               │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                              │                                           │
│                              ▼                                           │
│                    ┌─────────────────────┐                              │
│                    │   Validated Issues  │                              │
│                    │   (M개, M ≤ N)       │                              │
│                    └─────────────────────┘                              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Design

### 3.1 Core Components

```
review_agent/
├── main.py                 # Entry point
├── config.py               # Configuration
├── pipeline/
│   ├── __init__.py
│   ├── stage1_identify.py  # Issue identification
│   └── stage2_validate.py  # Issue validation
├── tools/
│   ├── __init__.py
│   ├── storage_tool.py     # Structured output collection
│   ├── github_tool.py      # GitHub API wrapper
│   └── diff_parser.py      # Git diff parsing
├── models/
│   ├── __init__.py
│   ├── issue.py            # Issue data model
│   └── review.py           # Review comment model
└── utils/
    ├── __init__.py
    └── logging.py
```

### 3.2 Data Models

```python
# models/issue.py
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List

class Severity(Enum):
    CRITICAL = "critical"   # 보안, 데이터 손실
    HIGH = "high"           # 버그, 성능 심각
    MEDIUM = "medium"       # 코드 품질
    LOW = "low"             # 스타일, 제안

class IssueType(Enum):
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    LOGIC_ERROR = "logic_error"
    TYPE_ERROR = "type_error"
    UNUSED_CODE = "unused_code"
    BEST_PRACTICE = "best_practice"

@dataclass
class PotentialIssue:
    """Stage 1 output"""
    file_path: str
    line_start: int
    line_end: int
    issue_type: IssueType
    severity: Severity
    description: str
    code_snippet: str

@dataclass
class ValidatedIssue:
    """Stage 2 output"""
    issue: PotentialIssue
    is_valid: bool
    evidence: List[str]           # 코드베이스에서 찾은 근거
    library_reference: Optional[str]  # 라이브러리 문서 참조
    mitigation: Optional[str]     # 해결 방안
    confidence: float             # 0.0 ~ 1.0
```

### 3.3 Storage Tool Pattern

```python
# tools/storage_tool.py
from typing import List, Any, TypeVar, Generic
from dataclasses import dataclass

T = TypeVar('T')

class StorageTool(Generic[T]):
    """
    에이전트의 출력을 구조화된 형태로 수집.
    Tool Call을 데이터 전송 레이어로 활용.
    """

    def __init__(self):
        self._values: List[T] = []

    def store(self, value: T) -> str:
        """에이전트가 호출하는 도구 함수"""
        self._values.append(value)
        return f"Stored successfully. Total: {len(self._values)}"

    @property
    def values(self) -> List[T]:
        return self._values.copy()

    def clear(self):
        self._values.clear()
```

---

## 4. Authentication Strategy

### 4.1 Claude Code Max 구독 활용

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Authentication Flow                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Option A: Self-hosted GitHub Runner                                     │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐     │
│   │ Company      │    │ Claude Code  │    │ GitHub Actions       │     │
│   │ Server       │ ─▶ │ OAuth Login  │ ─▶ │ Self-hosted Runner   │     │
│   │              │    │ (1회)        │    │ (인증 유지)          │     │
│   └──────────────┘    └──────────────┘    └──────────────────────┘     │
│                                                                          │
│  Option B: OAuth Token Caching                                           │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐     │
│   │ Claude Code  │    │ Auth Token   │    │ GitHub Secrets       │     │
│   │ Login        │ ─▶ │ Export       │ ─▶ │ CLAUDE_AUTH_TOKEN    │     │
│   └──────────────┘    └──────────────┘    └──────────────────────┘     │
│                                                                          │
│                              │                                           │
│                              ▼                                           │
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  GitHub Actions Workflow                                         │   │
│   │                                                                  │   │
│   │  env:                                                            │   │
│   │    CLAUDE_AUTH_TOKEN: ${{ secrets.CLAUDE_AUTH_TOKEN }}          │   │
│   │                                                                  │   │
│   │  # Claude Agent SDK uses Claude Code CLI backend                │   │
│   │  # No ANTHROPIC_API_KEY needed                                  │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Configuration

```yaml
# .github/workflows/pr-review.yml
name: AI PR Review

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  review:
    runs-on: self-hosted  # Option A
    # runs-on: ubuntu-latest  # Option B with token caching

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install claude-agent-sdk
          pip install uv  # for serena MCP

      - name: Run Review Agent
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          # Option B only:
          # CLAUDE_AUTH_TOKEN: ${{ secrets.CLAUDE_AUTH_TOKEN }}
        run: |
          python review_agent/main.py \
            --pr-number ${{ github.event.pull_request.number }} \
            --repo ${{ github.repository }}
```

---

## 5. Implementation Details

### 5.1 Main Entry Point

```python
# main.py
import argparse
from claude_agent_sdk import Agent
from pipeline.stage1_identify import identify_issues
from pipeline.stage2_validate import validate_issues
from tools.github_tool import GitHubTool
from tools.diff_parser import parse_pr_diff

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pr-number', type=int, required=True)
    parser.add_argument('--repo', type=str, required=True)
    args = parser.parse_args()

    # Initialize
    github = GitHubTool(args.repo, args.pr_number)

    # Get PR diff
    hunks = parse_pr_diff(github.get_diff())

    # Stage 1: Identify potential issues
    potential_issues = identify_issues(hunks)
    print(f"Stage 1: Found {len(potential_issues)} potential issues")

    # Stage 2: Validate issues
    validated_issues = validate_issues(potential_issues)
    valid_count = sum(1 for i in validated_issues if i.is_valid)
    print(f"Stage 2: {valid_count} valid issues (filtered {len(potential_issues) - valid_count} false positives)")

    # Post reviews
    for issue in validated_issues:
        if issue.is_valid and issue.confidence >= 0.7:
            github.post_review_comment(issue)

    print("Review completed!")

if __name__ == "__main__":
    main()
```

### 5.2 Stage 1: Issue Identification

```python
# pipeline/stage1_identify.py
from typing import List
from claude_agent_sdk import Agent
from tools.storage_tool import StorageTool
from models.issue import PotentialIssue

STAGE1_PROMPT = """
You are a code reviewer. Analyze the following code changes (hunks) and identify ALL potential issues.

Be aggressive in finding issues - it's okay to have false positives at this stage.
They will be filtered in the next stage.

Categories to look for:
- Bugs and logic errors
- Security vulnerabilities (XSS, injection, etc.)
- Performance issues
- Type errors
- Unused code
- Best practice violations

For each issue found, call the `store_issue` tool with:
- file_path: path to the file
- line_start/line_end: line numbers
- issue_type: one of [bug, security, performance, logic_error, type_error, unused_code, best_practice]
- severity: one of [critical, high, medium, low]
- description: clear explanation of the issue
- code_snippet: the problematic code

Hunks to analyze:
{hunks}
"""

def identify_issues(hunks: List[dict]) -> List[PotentialIssue]:
    storage = StorageTool[PotentialIssue]()

    agent = Agent(
        model="claude-sonnet-4-5",
        tools=[
            {
                "name": "store_issue",
                "description": "Store a potential issue found in the code",
                "handler": storage.store,
                "schema": PotentialIssue.__annotations__
            }
        ],
        mcp_servers=["sequential-thinking"]  # 복잡한 추론 활용
    )

    agent.run(STAGE1_PROMPT.format(hunks=format_hunks(hunks)))

    return storage.values
```

### 5.3 Stage 2: Issue Validation

```python
# pipeline/stage2_validate.py
from typing import List
from claude_agent_sdk import Agent
from tools.storage_tool import StorageTool
from models.issue import PotentialIssue, ValidatedIssue

STAGE2_PROMPT = """
You are validating a potential code issue. Your job is to determine if this is a REAL issue or a FALSE POSITIVE.

Use the available tools to gather evidence:
1. Use `serena` to search the codebase for related code, usage patterns, and context
2. Use `context7` to look up library documentation if the issue involves external libraries

Potential Issue:
- File: {file_path}
- Lines: {line_start}-{line_end}
- Type: {issue_type}
- Description: {description}
- Code: {code_snippet}

After investigation, call `store_verdict` with:
- is_valid: true if this is a real issue, false if it's a false positive
- evidence: list of findings from codebase search
- library_reference: relevant documentation (if any)
- mitigation: how to fix (if valid)
- confidence: 0.0-1.0
"""

def validate_issues(potential_issues: List[PotentialIssue]) -> List[ValidatedIssue]:
    validated = []

    for issue in potential_issues:
        storage = StorageTool[ValidatedIssue]()

        agent = Agent(
            model="claude-sonnet-4-5",
            tools=[
                {
                    "name": "store_verdict",
                    "description": "Store the validation verdict",
                    "handler": lambda v: storage.store(ValidatedIssue(issue=issue, **v)),
                    "schema": {
                        "is_valid": bool,
                        "evidence": List[str],
                        "library_reference": str,
                        "mitigation": str,
                        "confidence": float
                    }
                }
            ],
            mcp_servers=["serena", "context7"]  # 검색 도구 활용
        )

        agent.run(STAGE2_PROMPT.format(
            file_path=issue.file_path,
            line_start=issue.line_start,
            line_end=issue.line_end,
            issue_type=issue.issue_type.value,
            description=issue.description,
            code_snippet=issue.code_snippet
        ))

        if storage.values:
            validated.append(storage.values[0])

    return validated
```

---

## 6. Review Output Format

### 6.1 GitHub PR Comment Structure

```markdown
## AI Code Review

### Issue Found: XSS Vulnerability

**Severity:** CRITICAL
**File:** `src/components/UserInput.tsx:42-45`

#### Description
User input is directly rendered without sanitization, allowing potential XSS attacks.

#### Evidence
- Found 3 other instances in codebase using `dangerouslySetInnerHTML` with proper sanitization
- React documentation recommends using DOMPurify for user-generated content

#### Suggested Fix
```tsx
import DOMPurify from 'dompurify';

// Before
<div dangerouslySetInnerHTML={{ __html: userInput }} />

// After
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(userInput) }} />
```

---

*Confidence: 95%*
*Reviewed by AI PR Review Agent*
```

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Precision | > 80% | Valid issues / Total reported |
| Recall | > 60% | Found issues / Actual issues |
| False Positive Rate | < 20% | False positives / Total reported |
| Review Time | < 3 min | Per PR average |
| Coverage | 100% | PRs reviewed / PRs opened |

---

## 8. Limitations & Future Work

### 8.1 Current Limitations
- Self-hosted runner 또는 토큰 관리 필요
- 대규모 PR에서 시간 소요 증가
- 복잡한 비즈니스 로직 이해 한계

### 8.2 Future Enhancements
- [ ] 학습 기반 오탐 감소 (피드백 루프)
- [ ] 리뷰어별 스타일 학습
- [ ] 멀티 리포지토리 지원
- [ ] Slack/Discord 알림 연동

---

## 9. Security Considerations

- GitHub Token은 최소 권한만 부여 (pull_request read/write)
- 코드는 외부로 전송되지 않음 (Claude Code 로컬 처리)
- Secrets는 GitHub Actions에서만 접근
- Self-hosted runner는 회사 네트워크 내 운영

---

## 10. Dependencies

```
# requirements.txt
claude-agent-sdk>=0.1.0
PyGithub>=2.1.0
unidiff>=0.7.5
pydantic>=2.0.0
pytest>=8.0.0
pytest-cov>=4.1.0
```

```json
// .mcp.json (already configured)
{
  "mcpServers": {
    "sequential-thinking": { ... },
    "context7": { ... },
    "serena": { ... }
  }
}
```

---

## 11. Extension: Multi-PR Orchestration (Phase 2)

> 단일 PR 에이전트가 stateless 순수 함수로 설계되어 있어, 아키텍처 수정 없이 레이어 추가만으로 확장 가능.

### 11.1 Orchestrator Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Multi-PR Orchestration                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                   Orchestrator (NEW LAYER)                       │    │
│  │                                                                  │    │
│  │   1. PR Queue 관리                                               │    │
│  │   2. 의존성 그래프 분석 (토폴로지 정렬)                          │    │
│  │   3. Conflict 예측                                               │    │
│  │   4. Merge 순서 결정                                             │    │
│  └──────────────────────────────┬──────────────────────────────────┘    │
│                                 │                                        │
│          ┌──────────────────────┼──────────────────────┐                │
│          ▼                      ▼                      ▼                │
│   ┌─────────────┐        ┌─────────────┐        ┌─────────────┐        │
│   │Review Agent │        │Review Agent │        │Review Agent │        │
│   │  PR #101    │        │  PR #102    │        │  PR #103    │        │
│   │  (기존대로) │        │  (기존대로) │        │  (기존대로) │        │
│   └──────┬──────┘        └──────┬──────┘        └──────┬──────┘        │
│          │                      │                      │                │
│          └──────────────────────┴──────────────────────┘                │
│                                 │                                        │
│                                 ▼                                        │
│                    ┌─────────────────────────┐                          │
│                    │     Merge Executor      │                          │
│                    │                         │                          │
│                    │  1. Conflict 체크       │                          │
│                    │  2. 순차 Merge          │                          │
│                    │  3. CI 확인             │                          │
│                    │  4. Rollback (실패시)   │                          │
│                    └─────────────────────────┘                          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 11.2 Orchestrator Data Model

```python
# models/orchestrator.py
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict

class PRStatus(Enum):
    PENDING = "pending"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    MERGED = "merged"
    FAILED = "failed"
    CONFLICT = "conflict"

@dataclass
class PRNode:
    pr_number: int
    branch: str
    base: str                    # target branch
    status: PRStatus
    depends_on: List[int]        # 의존하는 PR 번호들
    conflicts_with: List[int]    # 충돌 가능성 있는 PR
    changed_files: List[str]     # 변경된 파일 목록

class PROrchestrator:
    def __init__(self):
        self.queue: Dict[int, PRNode] = {}

    def analyze_dependencies(self) -> List[List[int]]:
        """토폴로지 정렬로 병렬 실행 가능한 그룹 반환"""
        ...

    def predict_conflicts(self, pr_a: int, pr_b: int) -> bool:
        """두 PR의 변경 파일이 겹치는지 확인"""
        files_a = set(self.queue[pr_a].changed_files)
        files_b = set(self.queue[pr_b].changed_files)
        return bool(files_a & files_b)

    def get_merge_order(self) -> List[int]:
        """의존성과 충돌을 고려한 최적 merge 순서"""
        ...
```

### 11.3 Merge Executor

```python
# pipeline/merge_executor.py
class MergeExecutor:
    async def execute_merge_plan(self, pr_order: List[int]):
        for pr_number in pr_order:
            # 1. 최신 base와 충돌 체크
            if await self.has_conflicts(pr_number):
                success = await self.attempt_auto_rebase(pr_number)
                if not success:
                    await self.notify_conflict(pr_number)
                    continue

            # 2. CI 통과 확인
            if not await self.ci_passed(pr_number):
                await self.notify_ci_failure(pr_number)
                continue

            # 3. Merge 실행
            await self.github.merge_pr(pr_number, method="squash")
```

### 11.4 확장 시 기존 코드 수정량

| 컴포넌트 | 수정 필요 | 설명 |
|----------|-----------|------|
| Review Agent | ❌ 없음 | Stateless 순수 함수 |
| Stage 1, 2 | ❌ 없음 | 그대로 사용 |
| Storage Tool | ❌ 없음 | 그대로 사용 |
| MCP 설정 | ❌ 없음 | 그대로 사용 |
| **Orchestrator** | ✅ 추가 | 새 레이어 |
| **Merge Executor** | ✅ 추가 | 새 레이어 |

---

## 12. Extension: TDD-Based Coverage Gate (Phase 3)

> 테스트 자동 생성 및 커버리지 기반 Merge 결정 시스템.

### 12.0 Test Generation Timing

테스트 자동 생성의 트리거 시점:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Test Generation Trigger Flow                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   PR Created ──▶ Stage 1,2 Review ──▶ Issues Found?                     │
│                                              │                           │
│                              ┌───────────────┴───────────────┐          │
│                              ▼                               ▼          │
│                         Yes: Issues                    No: Clean        │
│                              │                               │          │
│                              ▼                               ▼          │
│                     Developer Fixes ◀────────┐    Ready for Merge       │
│                              │               │           │              │
│                              ▼               │           ▼              │
│                      Re-review ──────────────┘    ┌─────────────┐       │
│                                                   │ TRIGGER:    │       │
│                                                   │ Test Gen    │       │
│                                                   │ Stage 3 & 4 │       │
│                                                   └──────┬──────┘       │
│                                                          │              │
│                                    ┌─────────────────────┴──────┐       │
│                                    ▼                            ▼       │
│                              Tests Pass              Tests Fail         │
│                              Coverage OK             Coverage Low       │
│                                    │                            │       │
│                                    ▼                            ▼       │
│                              ✅ AUTO MERGE            ❌ BLOCK          │
│                                                    (Notify Dev)         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

Trigger Conditions:
1. PR has passed Stage 1,2 review (no critical/high issues)
2. All reviewer comments addressed
3. CI checks passing
4. Ready for merge label added OR merge requested

Why "Merge 직전" timing:
- 효율성: 완성된 코드에만 테스트 생성 (리소스 절약)
- 품질: 리뷰 통과 후 안정화된 코드 기준
- 실용성: 테스트가 실제 merge되는 코드와 일치
```

### 12.1 Extended Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    TDD-Based 4-Stage Pipeline                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Stage 1: Issue Identification      (기존)                               │
│  Stage 2: Issue Validation          (기존)                               │
│  Stage 3: Test Generation           (NEW)                                │
│  Stage 4: Coverage Gate             (NEW)                                │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Stage 3: Test Generation                                        │    │
│  │                                                                  │    │
│  │   Input: PR Diff + Validated Issues                             │    │
│  │                                                                  │    │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐    │    │
│  │   │ 변경된 함수 │ ─▶ │ 테스트 케이스│ ─▶ │ 테스트 파일    │    │    │
│  │   │ 분석        │    │ 생성         │    │ 작성           │    │    │
│  │   └─────────────┘    └─────────────┘    └─────────────────┘    │    │
│  │                                                                  │    │
│  │   Rules:                                                         │    │
│  │   - 변경된 함수마다 최소 3개 테스트 (happy/edge/error)          │    │
│  │   - 기존 테스트 스타일 따르기 (serena로 패턴 검색)              │    │
│  │   - 발견된 이슈마다 회귀 테스트 추가                            │    │
│  │                                                                  │    │
│  │   Tools: serena, context7                                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                 │                                        │
│                                 ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Stage 4: Coverage Gate                                          │    │
│  │                                                                  │    │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐    │    │
│  │   │ 테스트 실행 │ ─▶ │ 커버리지    │ ─▶ │ Merge 결정     │    │    │
│  │   │ (pytest/    │    │ 분석        │    │                 │    │    │
│  │   │  jest)      │    │             │    │ ✅ Approve      │    │    │
│  │   └─────────────┘    └─────────────┘    │ ❌ Block        │    │    │
│  │                                          └─────────────────┘    │    │
│  │   Tools: Bash, playwright (E2E)                                 │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 12.2 Test Generation Data Models

```python
# models/test.py
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class GeneratedTest:
    file_path: str               # tests/test_new_feature.py
    content: str                 # 테스트 코드
    covers_functions: List[str]  # 커버하는 함수들
    covers_issues: List[int]     # 커버하는 이슈 번호
    test_type: str               # unit, integration, e2e

@dataclass
class CoverageResult:
    total_coverage: float        # 전체 커버리지 %
    new_code_coverage: float     # 새 코드만 커버리지 %
    uncovered_lines: List[str]   # 커버 안 된 라인들
    tests_passed: int
    tests_failed: int
    test_duration_seconds: float

@dataclass
class MergeDecision:
    approved: bool
    reason: str
    coverage: CoverageResult
    conditions_met: dict         # 각 조건 통과 여부
    generated_tests_count: int
```

### 12.3 Merge Rules Configuration

```python
# config.py
from dataclasses import dataclass

@dataclass
class MergeRules:
    # 커버리지 기준
    min_total_coverage: float = 80.0       # 전체 80% 이상
    min_new_code_coverage: float = 90.0    # 새 코드 90% 이상

    # 테스트 기준
    all_tests_must_pass: bool = True
    min_tests_per_function: int = 2
    require_edge_case_tests: bool = True

    # 이슈 기준
    allow_low_severity_issues: bool = True
    block_on_critical: bool = True
    block_on_high: bool = True
    max_medium_issues: int = 3

    # 자동화 수준
    auto_merge_on_pass: bool = False       # True면 조건 충족시 자동 Merge
    auto_commit_tests: bool = True         # 생성된 테스트를 PR에 커밋
    auto_fix_simple_issues: bool = False   # 간단한 이슈 자동 수정
```

### 12.4 Stage 3: Test Generation Implementation

```python
# pipeline/stage3_test_gen.py

TEST_GEN_PROMPT = """
You are a TDD expert. Generate comprehensive test cases for the code changes.

## Rules
1. 각 변경된 함수/메서드마다:
   - Happy path 테스트 (정상 동작)
   - Edge case 테스트 (경계값, null, empty)
   - Error case 테스트 (예외 처리)

2. 기존 테스트 스타일 따르기:
   - serena로 기존 테스트 파일 검색
   - 동일한 패턴, 네이밍, 구조 사용

3. 발견된 이슈에 대한 회귀 테스트:
   - 각 validated issue에 대해 테스트 추가
   - "이 테스트가 통과하면 이슈가 해결된 것"

## PR Changes
{pr_diff}

## Validated Issues
{validated_issues}

## Instructions
1. serena로 기존 테스트 패턴 검색
2. context7로 테스트 프레임워크 문서 참조
3. store_test 도구로 각 테스트 파일 저장
"""

async def generate_tests(
    pr_diff: str,
    validated_issues: List[ValidatedIssue]
) -> List[GeneratedTest]:
    storage = StorageTool[GeneratedTest]()

    agent = Agent(
        model="claude-sonnet-4-5",
        tools=[
            {
                "name": "store_test",
                "description": "Store a generated test file",
                "handler": storage.store,
                "schema": GeneratedTest.__annotations__
            }
        ],
        mcp_servers=["serena", "context7"]
    )

    agent.run(TEST_GEN_PROMPT.format(
        pr_diff=pr_diff,
        validated_issues=format_issues(validated_issues)
    ))

    return storage.values
```

### 12.5 Stage 4: Coverage Gate Implementation

```python
# pipeline/stage4_coverage.py

class CoverageGate:
    def __init__(self, rules: MergeRules):
        self.rules = rules

    async def execute(
        self,
        generated_tests: List[GeneratedTest],
        validated_issues: List[ValidatedIssue]
    ) -> MergeDecision:

        # 1. 생성된 테스트 파일 작성
        for test in generated_tests:
            await self.write_test_file(test)

        # 2. 테스트 실행 + 커버리지 측정
        coverage = await self.run_tests_with_coverage()

        # 3. 룰 기반 Merge 결정
        conditions = self.check_conditions(coverage, validated_issues)

        approved = all(conditions.values())

        return MergeDecision(
            approved=approved,
            reason=self.generate_reason(conditions),
            coverage=coverage,
            conditions_met=conditions,
            generated_tests_count=len(generated_tests)
        )

    def check_conditions(
        self,
        coverage: CoverageResult,
        issues: List[ValidatedIssue]
    ) -> dict:
        return {
            "all_tests_pass": coverage.tests_failed == 0,
            "min_coverage_met": coverage.new_code_coverage >= self.rules.min_new_code_coverage,
            "no_critical_issues": not any(
                i.is_valid and i.issue.severity.value == "critical"
                for i in issues
            ),
            "no_high_issues": not any(
                i.is_valid and i.issue.severity.value == "high"
                for i in issues
            ) if self.rules.block_on_high else True,
        }

    async def run_tests_with_coverage(self) -> CoverageResult:
        # Python 프로젝트
        result = await bash.run(
            "pytest --cov=src --cov-report=json --cov-report=term tests/"
        )
        return self.parse_pytest_coverage(result)
```

### 12.6 Complete Flow Example

```
PR #123 Created (feature/user-auth)
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 1 & 2: Code Review                                    │
│ Result: 5 potential → 2 valid issues (medium severity)      │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: Test Generation                                    │
│ Generated:                                                  │
│   - test_login_success.py (happy path)                     │
│   - test_login_edge_cases.py (empty password, etc)         │
│   - test_login_errors.py (invalid credentials)             │
│   - test_issue_42_regression.py (for validated issue)      │
│ Total: 12 test cases                                        │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: Coverage Gate                                      │
│                                                             │
│ Test Results:                                               │
│   ✅ 12/12 tests passed                                    │
│   ✅ New code coverage: 94% (>= 90%)                       │
│   ✅ Total coverage: 82% (>= 80%)                          │
│                                                             │
│ Issue Check:                                                │
│   ✅ No critical issues                                    │
│   ✅ No high issues                                        │
│   ⚠️  2 medium issues (allowed)                            │
│                                                             │
│ ════════════════════════════════════════════════════════   │
│ DECISION: ✅ APPROVED FOR MERGE                            │
│ ════════════════════════════════════════════════════════   │
│                                                             │
│ Actions:                                                    │
│   1. Commit 12 generated tests to PR branch                │
│   2. Post summary comment with coverage report             │
│   3. Auto-merge (if enabled)                               │
└─────────────────────────────────────────────────────────────┘
```

### 12.7 Phase 3 확장 시 기존 코드 수정량

| 컴포넌트 | 수정 필요 | 설명 |
|----------|-----------|------|
| Stage 1, 2 | ❌ 없음 | 그대로 사용 |
| Storage Tool | ❌ 없음 | 새 타입만 추가 |
| MCP 설정 | ❌ 없음 | 그대로 사용 |
| **Stage 3** | ✅ 추가 | 테스트 생성 |
| **Stage 4** | ✅ 추가 | 커버리지 게이트 |
| **MergeRules** | ✅ 추가 | 설정 확장 |

---

## 13. Implementation Roadmap

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Implementation Phases                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Phase 1: Single PR Review (MVP) ✅ COMPLETE                             │
│  ───────────────────────────────                                         │
│  - Stage 1 & 2 구현                                                      │
│  - GitHub Actions 연동                                                   │
│  - 기본 리뷰 코멘트                                                      │
│  - 목표: POC 완성                                                        │
│                                                                          │
│  Phase 1.5: Performance Optimization ✅ COMPLETE                         │
│  ────────────────────────────────────                                    │
│  - Stage 2 병렬 실행 (--parallel 기본 활성화)                            │
│  - Stage 1에서 low severity 필터링                                       │
│  - 결과: 20분 29초 → 4분 20초 (79% 개선)                                 │
│                                                                          │
│  Phase 2: Multi-PR Orchestration ✅ COMPLETE                             │
│  ───────────────────────────────                                         │
│  - Orchestrator 레이어 추가 (orchestrator/ 모듈)                         │
│  - 의존성 그래프 분석 (topological sort)                                 │
│  - 자동 Merge 기능 (MergeExecutor)                                       │
│  - Conflict 감지 (ConflictPredictor)                                     │
│  - CLI: orchestrate --repo owner/repo --dry-run                          │
│                                                                          │
│  Phase 3: TDD Coverage Gate ✅ COMPLETE                                  │
│  ──────────────────────────                                              │
│  - Stage 3: Test Generation (AI 기반 테스트 생성)                        │
│  - Stage 4: Coverage Gate (커버리지 검증 및 Merge 결정)                  │
│  - 회귀 테스트 자동 생성 (validated issues 기반)                         │
│  - CLI: testgen --repo owner/repo --pr-number 1 --dry-run                │
│                                                                          │
│  Phase 4: Advanced (Future)                                              │
│  ─────────────────────────                                               │
│  - Conflict 자동 해결 Agent                                              │
│  - 피드백 기반 학습                                                      │
│  - 멀티 리포지토리                                                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```
