# AI PR Review Agent

Claude Agent SDK를 활용한 AI 기반 PR 코드 리뷰 에이전트.

**API Key 없이** Claude Code Max 구독만으로 운영 가능.

---

## 설치

### 1. 레포에서 초기화

```bash
cd /path/to/your-repo
uv run review-agent init
git add . && git commit -m "Add AI PR Review" && git push
```

### 2. Self-hosted Runner 등록

GitHub 웹에서:
1. 레포 → Settings → Actions → Runners
2. "New self-hosted runner" 클릭
3. 안내에 따라 설치 (다운로드 → 압축 해제 → `./config.sh`)

### 3. Runner 실행

```bash
./run.sh
```

**끝.** 이후 PR 생성 시 자동으로 리뷰가 실행됩니다.

---

## 수동 실행 (선택)

특정 PR을 직접 리뷰하고 싶을 때:

```bash
uv run review-agent review --repo YOUR_USERNAME/YOUR_REPO --pr-number 123
```

---

## License

MIT
