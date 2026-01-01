# AI PR Review Agent

Claude Agent SDK를 활용한 AI 기반 PR 코드 리뷰 에이전트.

**API Key 없이** Claude Code Max 구독만으로 운영 가능.

## Features

- **2-Stage Pipeline**: Recall 우선 이슈 탐지 → Precision 우선 검증
- **MCP 서버 통합**: serena (코드검색), context7 (문서검색), sequential-thinking (추론)
- **GitHub 연동**: PR 코멘트 자동 게시
- **확장 가능**: Multi-PR Orchestration, TDD Coverage Gate (Phase 2, 3)

## Architecture

```
PR Created → GitHub Actions → Review Agent
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
            Stage 1: Identify              Stage 2: Validate
            (sequential-thinking)          (serena + context7)
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                            GitHub PR Comments
```

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (패키지 매니저)
- Node.js 20+ (MCP 서버용)
- Claude Code Max 구독 (Self-hosted runner) 또는 Anthropic API Key

---

## Quick Start (다른 레포에 설치)

```bash
# 1. 대상 레포로 이동
cd /path/to/your-repo

# 2. 초기화 (workflow와 설정 파일 자동 생성)
uvx --from git+https://github.com/owner/review-agent review-agent init

# 3. 커밋 & 푸시
git add .
git commit -m "Add AI PR Review Agent"
git push
```

**이게 끝입니다!** 이후 PR 생성 시 자동으로 리뷰가 실행됩니다.

---

## 어떻게 작동하나요?

### 자동 실행 원리

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         전체 흐름                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. 개발자가 코드 수정                                                   │
│        │                                                                 │
│        ▼                                                                 │
│  2. git push (새 브랜치)                                                 │
│        │                                                                 │
│        ▼                                                                 │
│  3. GitHub에서 PR 생성                                                   │
│        │                                                                 │
│        ▼                                                                 │
│  4. GitHub가 .github/workflows/*.yml 파일 확인                          │
│        │                                                                 │
│        ▼                                                                 │
│  5. "pull_request" 이벤트와 매칭되는 workflow 실행                       │
│        │                                                                 │
│        ▼                                                                 │
│  6. Runner 서버에서 review-agent 자동 실행                               │
│        │                                                                 │
│        ▼                                                                 │
│  7. PR에 코멘트 자동 게시                                                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### GitHub Actions란?

GitHub는 레포지토리에 `.github/workflows/` 폴더가 있으면 자동으로 감시합니다.

```yaml
# .github/workflows/pr-review.yml

on:
  pull_request:                    # ← "PR 이벤트가 발생하면"
    types: [opened, synchronize]   # ← "PR 생성 또는 업데이트 시"

jobs:
  review:
    runs-on: self-hosted           # ← "이 서버에서"
    steps:
      - run: review-agent review   # ← "이 명령어를 실행해라"
```

### 비유로 설명

```
GitHub Actions = 자동 문지기

.github/workflows/pr-review.yml = 문지기에게 주는 지시서
   "누가 PR을 올리면, review-agent를 실행해서 검사해줘"

Self-hosted Runner = 문지기가 일하는 사무실 (컴퓨터)

GITHUB_TOKEN = 문지기의 신분증 (PR에 코멘트 달 권한)
```

---

## 레포지토리 연결 방법

### 방법 1: 자동 설치 (권장)

```bash
# 대상 레포에서 한 줄로 설치
cd /path/to/your-repo
uvx --from git+https://github.com/owner/review-agent review-agent init
```

이 명령어가 자동으로 생성하는 파일:
- `.github/workflows/pr-review.yml` - GitHub Actions 워크플로우
- `.mcp.json` - MCP 서버 설정

### 방법 2: 로컬에서 설치

```bash
cd /Users/jwcorp/test_pr
uv run review-agent init /path/to/target-repo
```

### 방법 3: 수동 복사

```bash
# 대상 레포로 파일 복사
cp -r review_agent/ /path/to/target-repo/
cp .github/workflows/pr-review.yml /path/to/target-repo/.github/workflows/
cp .mcp.json /path/to/target-repo/
cp pyproject.toml /path/to/target-repo/
```

---

## 두 가지 사용 방식

### 1. 자동 실행 (init 후 PR 생성)

```bash
# 한 번만 설정
review-agent init
git add . && git commit -m "Add AI PR Review" && git push

# 이후 모든 PR에서 자동 실행
# PR 생성 → GitHub Actions 트리거 → 자동 리뷰 → 코멘트 게시
```

### 2. 수동 실행 (특정 PR 직접 리뷰)

```bash
# 로컬에서 특정 PR 리뷰
review-agent review --repo owner/repo --pr-number 123
```

### 비교

| 방법 | 사용 시점 | 자동화 |
|------|----------|--------|
| `init` → PR 생성 | 지속적인 자동 리뷰 | ✅ 자동 (PR마다) |
| `review --repo --pr-number` | 일회성 테스트, 디버깅 | ❌ 수동 |

---

## Installation (개발용)

```bash
# uv 설치
curl -LsSf https://astral.sh/uv/install.sh | sh

# 클론
git clone https://github.com/owner/review-agent
cd review-agent

# 의존성 설치
uv sync --dev
```

## CLI 명령어

```bash
# 도움말
uv run review-agent --help

# 레포에 설치
uv run review-agent init [path]

# PR 리뷰 실행
uv run review-agent review --repo owner/repo --pr-number 123

# 옵션
uv run review-agent review \
  --repo owner/repo \
  --pr-number 123 \
  --min-confidence 0.8 \
  --report-low \
  --parallel \
  --debug
```

## 환경 변수

```bash
export GITHUB_TOKEN="ghp_..."
export GITHUB_REPOSITORY="owner/repo"
export PR_NUMBER="123"

uv run review-agent review
```

---

## Project Structure

```
review_agent/
├── main.py                 # CLI 엔트리포인트
├── config.py               # 설정 (ReviewConfig, MergeRules)
├── cli/
│   └── init_cmd.py         # init 명령어 (레포 설치)
├── models/
│   └── issue.py            # PotentialIssue, ValidatedIssue
├── pipeline/
│   ├── stage1_identify.py  # Stage 1: 이슈 탐지 (Recall 우선)
│   └── stage2_validate.py  # Stage 2: 이슈 검증 (Precision 우선)
├── tools/
│   ├── storage_tool.py     # 구조화된 출력 수집
│   ├── github_tool.py      # GitHub API 래퍼
│   └── diff_parser.py      # Git diff 파싱
└── utils/
    └── logging.py          # 로깅 유틸리티
```

---

## How It Works

### Stage 1: Issue Identification (Recall 우선)

- `sequential-thinking` MCP로 복잡한 추론
- 모든 잠재적 이슈 도출 (false positive 허용)
- 카테고리: bug, security, performance, logic_error, type_error, unused_code, best_practice

### Stage 2: Issue Validation (Precision 우선)

- `serena`로 코드베이스 검색 (패턴, 사용례)
- `context7`로 라이브러리 문서 검색
- 근거 기반 검증으로 false positive 제거

---

## Configuration

```python
# config.py
@dataclass
class ReviewConfig:
    min_confidence: float = 0.7   # 최소 신뢰도
    report_critical: bool = True  # Critical 이슈 리포트
    report_high: bool = True      # High 이슈 리포트
    report_medium: bool = True    # Medium 이슈 리포트
    report_low: bool = False      # Low 이슈 리포트 (기본 OFF)
```

---

## MCP Servers

프로젝트에서 사용하는 MCP 서버:

| 서버 | 용도 | Stage |
|------|------|-------|
| sequential-thinking | 복잡한 추론 | Stage 1 |
| serena | 코드베이스 검색 | Stage 2 |
| context7 | 라이브러리 문서 | Stage 2 |

`.mcp.json`에 설정되어 있습니다.

---

## Self-hosted Runner 설정

Claude Code Max 인증을 유지하려면 Self-hosted runner가 필요합니다.

```bash
# 1. Self-hosted runner 설치 (회사 서버 또는 로컬)
# GitHub repo → Settings → Actions → Runners → New self-hosted runner

# 2. Runner에서 Claude Code 로그인 (1회)
claude login

# 3. Runner 시작
./run.sh
```

---

## Roadmap

- [x] **Phase 1**: Single PR Review (MVP)
- [ ] **Phase 2**: Multi-PR Orchestration
- [ ] **Phase 3**: TDD-Based Coverage Gate
- [ ] **Phase 4**: Conflict Auto-Resolution

자세한 내용은 [PRD.md](PRD.md) 참조.

---

## Development

```bash
# 테스트
uv run pytest

# 커버리지
uv run pytest --cov=review_agent --cov-report=html

# 린트
uv run ruff check .

# 타입 체크
uv run mypy review_agent
```

---

## FAQ

### Q: init 후에 뭘 더 해야 하나요?
A: 없습니다. 커밋/푸시만 하면 이후 모든 PR에서 자동 실행됩니다.

### Q: API Key가 필요한가요?
A: Claude Code Max 구독이 있으면 불필요합니다. Self-hosted runner에서 `claude login`만 하면 됩니다.

### Q: 여러 레포에 설치할 수 있나요?
A: 네. 각 레포에서 `review-agent init`을 실행하면 됩니다.

### Q: 수동으로 특정 PR만 리뷰할 수 있나요?
A: 네. `review-agent review --repo owner/repo --pr-number 123`

---

## License

MIT

## References

- [Hyperithm Review Agent](https://tech.hyperithm.com/review-agent)
- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)
- [Serena MCP](https://github.com/oraios/serena)
- [Context7 MCP](https://context7.com)
