# AI PR Review Agent

Claude Agent SDK를 활용한 AI 기반 PR 코드 리뷰 에이전트.

**API Key 없이** Claude Code Max 구독만으로 운영 가능.

## Features

- **2-Stage Review**: Issue 발굴 (Stage 1) → 근거 기반 검증 (Stage 2)
- **Auto Fix**: 발견된 버그 자동 수정
- **Feedback Loop**: Review → Fix → Re-review → Merge 자동화
- **Integration Tests**: SQL injection, Command injection 등 검증됨

---

## Quick Start

### 1. 설치

```bash
cd /path/to/your-repo
git clone https://github.com/ico1036/test_pr.git
cd test_pr
uv sync
```

### 2. 사용법

#### PR 리뷰만 (코멘트 작성)
```bash
GITHUB_TOKEN=$(gh auth token) uv run python -m review_agent.main review \
  --repo owner/repo \
  --pr-number 123
```

#### Autofix (리뷰 + 수정 + 머지)
```bash
GITHUB_TOKEN=$(gh auth token) uv run python -m review_agent.main autofix \
  --repo owner/repo \
  --pr-number 123
```

---

## CLI Commands

### `review` - PR 리뷰
```bash
python -m review_agent.main review \
  --repo owner/repo \
  --pr-number 123 \
  --min-severity medium \
  --parallel
```

| Option | Description |
|--------|-------------|
| `--min-severity` | 최소 심각도 (low/medium/high/critical) |
| `--parallel` | Stage 2 병렬 실행 (기본값) |
| `--no-comments` | 코멘트 작성 안 함 |

### `autofix` - 자동 수정 + 머지
```bash
python -m review_agent.main autofix \
  --repo owner/repo \
  --pr-number 123 \
  --max-iterations 5 \
  --run-tests \
  --test-command "pytest"
```

| Option | Description |
|--------|-------------|
| `--max-iterations` | 최대 반복 횟수 (기본: 5) |
| `--min-severity` | 수정할 최소 심각도 (기본: medium) |
| `--no-auto-merge` | 자동 머지 비활성화 |
| `--run-tests` | 수정 후 테스트 실행 |
| `--test-command` | 테스트 명령어 (기본: pytest) |

### `orchestrate` - 다중 PR 관리
```bash
python -m review_agent.main orchestrate \
  --repo owner/repo \
  --dry-run \
  --auto-merge
```

---

## Workflow

```
PR Created
    │
    ▼
┌─────────────────────────────────┐
│ Stage 1: Issue Identification   │
│ (Recall 우선, 오탐 허용)        │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Stage 2: Issue Validation       │
│ (Precision 우선, 근거 기반)     │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Autofix Loop                    │
│ Fix → Commit → Re-review        │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Auto Merge (if clean)           │
└─────────────────────────────────┘
```

---

## Result Types

| Result | Description |
|--------|-------------|
| `MERGED` | PR 자동 머지 완료 |
| `READY_TO_MERGE` | 이슈 없음, 머지 준비 완료 |
| `UNFIXABLE` | 수정 불가능한 이슈 존재 |
| `TEST_FAILED` | 테스트 실패 |
| `MAX_ITERATIONS` | 최대 반복 도달 |

---

## GitHub Actions Integration

### Self-hosted Runner 설정

1. GitHub 웹 → Settings → Actions → Runners
2. "New self-hosted runner" 클릭
3. 안내에 따라 설치
4. Claude Code로 인증: `claude auth login`

### Workflow 예시

```yaml
# .github/workflows/autofix.yml
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
        with:
          fetch-depth: 0

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install uv && uv sync

      - name: Run Autofix
        run: |
          uv run python -m review_agent.main autofix \
            --repo ${{ github.repository }} \
            --pr-number ${{ github.event.pull_request.number }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Development

### 통합 테스트 실행

```bash
# 단일 테스트
GITHUB_TOKEN=$(gh auth token) uv run python tests/integration/test_feedback_loop.py sql_injection

# 전체 테스트
GITHUB_TOKEN=$(gh auth token) uv run python tests/integration/test_feedback_loop.py
```

### 테스트 케이스

| Test | Description |
|------|-------------|
| `sql_injection` | SQL injection 탐지 및 수정 |
| `command_injection` | Command injection 탐지 및 수정 |
| `division_by_zero` | Division by zero 탐지 및 수정 |
| `clean_code` | 클린 코드 통과 확인 |

---

## Requirements

- Python 3.11+
- Claude Code Max 구독 (인증 필요)
- GitHub Token (repo 권한)

---

## License

MIT
