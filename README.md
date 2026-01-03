# AI PR Review Agent

Claude Agent SDK 기반 PR 자동 리뷰 & 수정 & 머지 에이전트.

**API Key 없이** Claude Code Max 구독만으로 운영.

---

## Quick Start

### 1. Self-hosted Runner 설정

```bash
# 1. GitHub 웹 → Settings → Actions → Runners → "New self-hosted runner"
# 2. 안내에 따라 설치
# 3. Claude Code 인증
claude auth login
```

### 2. 프로젝트에 워크플로우 추가

`.github/workflows/ai-autofix.yml` 생성:

```yaml
name: AI Autofix

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write

jobs:
  autofix:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: astral-sh/setup-uv@v4

      - run: uv python install 3.11

      - run: |
          git clone https://github.com/ico1036/test_pr.git /tmp/review-agent
          cd /tmp/review-agent && uv sync

      - run: |
          cd /tmp/review-agent
          uv run review-agent autofix \
            --repo ${{ github.repository }} \
            --pr-number ${{ github.event.pull_request.number }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### 3. 끝!

PR 생성 시 자동으로:
1. 코드 리뷰 (보안, 버그, 성능 이슈 탐지)
2. 이슈 자동 수정
3. 자동 머지

---

## How It Works

```
PR Created → Stage 1 (이슈 발굴) → Stage 2 (검증) → Auto Fix → Auto Merge
```

| Result | Description |
|--------|-------------|
| `MERGED` | 자동 머지 완료 |
| `READY_TO_MERGE` | 이슈 없음 (auto_merge=False 시) |
| `UNFIXABLE` | 수정 불가 이슈 존재 |

---

## Requirements

- Self-hosted GitHub Actions Runner
- Claude Code Max 구독 (`claude auth login`)
- GitHub Token (자동 제공됨)

---

## License

MIT
