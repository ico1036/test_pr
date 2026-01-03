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
├── main.py                 # Entry point + CLI
├── config.py               # Configuration
├── pipeline/
│   ├── stage1_identify.py  # Issue identification
│   ├── stage2_validate.py  # Issue validation
│   ├── stage3_test_gen.py  # Test generation
│   ├── stage4_coverage.py  # Coverage gate
│   └── feedback_loop.py    # Autofix loop
├── orchestrator/           # Multi-PR management
├── tools/
│   ├── storage_tool.py     # Structured output collection
│   ├── github_tool.py      # GitHub API wrapper
│   └── diff_parser.py      # Git diff parsing
├── models/
│   ├── issue.py            # Issue data model
│   └── review.py           # Review comment model
└── utils/
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

## 5. CLI Usage

실제 사용법은 README.md 참조. 주요 명령어:

```bash
# PR 리뷰
review-agent review --repo owner/repo --pr-number 123

# 자동 수정 + 머지
review-agent autofix --repo owner/repo --pr-number 123

# 다중 PR 관리
review-agent orchestrate --repo owner/repo
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
- [x] ~~학습 기반 오탐 감소 (피드백 루프)~~ → Phase 3.5에서 구현
- [ ] 리뷰어별 스타일 학습
- [ ] 멀티 리포지토리 지원
- [ ] Slack/Discord 알림 연동
- [ ] pip 패키지 배포 (PyPI)

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

### 11.2 확장 시 기존 코드 수정량

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

### 12.2 Complete Flow Example

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

### 12.3 Phase 3 확장 시 기존 코드 수정량

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
│  Phase 3.5: Feedback Loop ✅ COMPLETE                                    │
│  ─────────────────────────────────────                                   │
│  - Review → Fix → Re-review → Merge 자동화                               │
│  - 이슈 자동 수정 (Claude Agent SDK)                                     │
│  - 중복 이슈 감지 (SHA256 해시)                                          │
│  - 파일 변경 검증 (before/after diff)                                    │
│  - Git commit/push 자동화                                                │
│  - 통합 테스트 (SQL injection, Command injection 등)                     │
│  - CLI: autofix --repo owner/repo --pr-number 1                          │
│                                                                          │
│  Phase 4: Distribution (Next)                                            │
│  ────────────────────────────                                            │
│  - pip 패키지 배포 (PyPI)                                                │
│  - GitHub Action 템플릿                                                  │
│  - 설치 스크립트 (install.sh)                                            │
│                                                                          │
│  Phase 5: Advanced (Future)                                              │
│  ─────────────────────────                                               │
│  - Conflict 자동 해결 Agent                                              │
│  - 피드백 기반 학습                                                      │
│  - 멀티 리포지토리                                                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 14. Extension: Feedback Loop (Phase 3.5) ✅ COMPLETE

> PR 리뷰만 하는 것이 아니라, 발견된 이슈를 자동으로 수정하고 다시 리뷰하여 머지까지 완료.

### 14.1 Feedback Loop Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Feedback Loop: Review → Fix → Merge                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   PR Created                                                             │
│       │                                                                  │
│       ▼                                                                  │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ ITERATION 1                                                      │   │
│   │                                                                  │   │
│   │   [1] Stage 1: Identify Issues                                   │   │
│   │       │                                                          │   │
│   │       ▼                                                          │   │
│   │   [2] Stage 2: Validate Issues                                   │   │
│   │       │                                                          │   │
│   │       ▼                                                          │   │
│   │   [3] Fix Issues (Claude Agent + Edit Tool)                      │   │
│   │       │                                                          │   │
│   │       ▼                                                          │   │
│   │   [4] Git Commit & Push                                          │   │
│   │       │                                                          │   │
│   └───────┼──────────────────────────────────────────────────────────┘   │
│           │                                                              │
│           ▼                                                              │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ ITERATION 2 (Re-review)                                          │   │
│   │                                                                  │   │
│   │   Issues Found?                                                  │   │
│   │       │                                                          │   │
│   │   ┌───┴───┐                                                      │   │
│   │   ▼       ▼                                                      │   │
│   │  Yes     No ──▶ READY_TO_MERGE ──▶ Auto Merge                   │   │
│   │   │                                                              │   │
│   │   ▼                                                              │   │
│   │  Continue Loop...                                                │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   Exit Conditions:                                                       │
│   - MERGED: PR successfully merged                                       │
│   - READY_TO_MERGE: Clean (auto_merge=False)                            │
│   - UNFIXABLE: Issues couldn't be fixed                                  │
│   - MAX_ITERATIONS: Hit iteration limit                                  │
│   - TEST_FAILED: Tests failed after fix                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 14.2 Data Models

```python
class LoopResult(Enum):
    MERGED = "merged"
    READY_TO_MERGE = "ready_to_merge"
    MAX_ITERATIONS = "max_iterations"
    UNFIXABLE = "unfixable"
    TEST_FAILED = "test_failed"
    ERROR = "error"

@dataclass
class LoopConfig:
    max_iterations: int = 5
    auto_fix: bool = True
    auto_merge: bool = True
    min_severity_to_fix: str = "medium"
    run_tests: bool = False
    test_command: str = "pytest"
```

### 14.3 CLI Usage

```bash
# Basic usage
python -m review_agent.main autofix \
  --repo owner/repo \
  --pr-number 123

# With options
python -m review_agent.main autofix \
  --repo owner/repo \
  --pr-number 123 \
  --max-iterations 3 \
  --run-tests \
  --no-auto-merge
```

### 14.4 Key Features

| Feature | Description |
|---------|-------------|
| Issue Deduplication | SHA256 hash로 중복 이슈 감지 |
| File Change Verification | 수정 전/후 파일 비교 |
| PR Diff Targeting | PR 변경 파일만 분석 |
| Test Verification | 수정 후 테스트 실행 |
| Auto Merge | 조건 충족시 자동 머지 |

---

## 15. Distribution Plan (Phase 4)

### 15.1 pip Package

```bash
pip install review-agent
review-agent autofix --repo owner/repo --pr-number 123
```

### 15.2 GitHub Action Template

```yaml
name: AI Autofix
on:
  pull_request:
    types: [opened, synchronize]
  issue_comment:
    types: [created]

jobs:
  autofix:
    runs-on: self-hosted
    if: |
      github.event_name == 'pull_request' ||
      contains(github.event.comment.body, '/autofix')
    steps:
      - uses: actions/checkout@v4
      - run: |
          pip install review-agent
          review-agent autofix \
            --repo ${{ github.repository }} \
            --pr-number ${{ github.event.pull_request.number }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```
