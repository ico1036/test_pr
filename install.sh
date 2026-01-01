#!/bin/bash
# AI PR Review Agent 설치 스크립트
# 사용법: curl -sSL https://raw.githubusercontent.com/owner/review-agent/main/install.sh | bash

set -e

REPO_URL="https://github.com/YOUR_USERNAME/YOUR_REPO"
BRANCH="main"

echo "Installing AI PR Review Agent..."

# 현재 디렉토리가 git repo인지 확인
if [ ! -d ".git" ]; then
    echo "Error: Not a git repository. Run this from your project root."
    exit 1
fi

# 임시 디렉토리에 클론
TMP_DIR=$(mktemp -d)
git clone --depth 1 -b "$BRANCH" "$REPO_URL" "$TMP_DIR"

# 필요한 파일 복사
echo "Copying files..."
cp -r "$TMP_DIR/review_agent" .
cp "$TMP_DIR/pyproject.toml" .
cp "$TMP_DIR/.mcp.json" .
mkdir -p .github/workflows
cp "$TMP_DIR/.github/workflows/pr-review.yml" .github/workflows/

# 정리
rm -rf "$TMP_DIR"

# uv 설치 확인
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# 의존성 설치
echo "Installing dependencies..."
uv lock
uv sync

echo ""
echo "Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Set up self-hosted runner or add ANTHROPIC_API_KEY to GitHub secrets"
echo "  2. git add . && git commit -m 'Add AI PR Review Agent'"
echo "  3. git push"
echo ""
