#!/bin/bash

# ========================================
# AUTO PUSH TO GITHUB - ONE COMMAND ONLY
# ========================================
# Usage: bash auto_push_github.sh <GITHUB_USERNAME> <GITHUB_TOKEN>
# Token: https://github.com/settings/tokens (centang: repo)

set -e

if [ $# -lt 2 ]; then
    echo "❌ Error: Missing arguments"
    echo ""
    echo "Usage: bash auto_push_github.sh <USERNAME> <TOKEN>"
    echo ""
    echo "Example:"
    echo "  bash auto_push_github.sh johndoe ghp_abc123xyz456"
    echo ""
    echo "Get token: https://github.com/settings/tokens"
    echo "  - Klik 'Generate new token (classic)'"
    echo "  - Centang: repo"
    echo "  - Copy token-nya"
    exit 1
fi

USERNAME=$1
TOKEN=$2
REPO_NAME="haru-checker"

echo "🚀 AUTO PUSH TO GITHUB"
echo "======================================"
echo "📦 Repo: $REPO_NAME"
echo "👤 User: $USERNAME"
echo "======================================"
echo ""

# 1. Create repo via GitHub API
echo "📝 Creating GitHub repo..."
RESPONSE=$(curl -s -X POST \
    -H "Authorization: token $TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    https://api.github.com/user/repos \
    -d "{\"name\":\"$REPO_NAME\",\"description\":\"Netflix Cookie Checker Bot - Production Ready\",\"private\":false,\"auto_init\":false}")

# Check if repo created or already exists
if echo "$RESPONSE" | grep -q '"id"'; then
    echo "✅ Repo created successfully!"
elif echo "$RESPONSE" | grep -q "already exists"; then
    echo "⚠️  Repo already exists, will use existing one"
else
    echo "❌ Failed to create repo:"
    echo "$RESPONSE"
    exit 1
fi

echo ""

# 2. Add remote and push
echo "📤 Pushing to GitHub..."

# Remove remote if exists
git remote remove origin 2>/dev/null || true

# Add remote with token
git remote add origin "https://${TOKEN}@github.com/${USERNAME}/${REPO_NAME}.git"

# Push to main branch
git branch -M main
git push -u origin main --force

echo ""
echo "======================================"
echo "✅ SELESAI! Bot sudah di GitHub"
echo "======================================"
echo ""
echo "🔗 Repo URL:"
echo "   https://github.com/${USERNAME}/${REPO_NAME}"
echo ""
echo "📥 Clone di Termux:"
echo "   cd ~"
echo "   git clone https://github.com/${USERNAME}/${REPO_NAME}.git"
echo "   cd ${REPO_NAME}"
echo "   pip install -r requirements.txt"
echo "   cp .env.example .env"
echo "   nano .env  # Isi BOT_TOKEN"
echo "   python bot.py"
echo ""
echo "🔄 Update kode nanti (di PocketDev):"
echo "   git add -A"
echo "   git commit -m 'Update: xxx'"
echo "   git push"
echo ""
echo "📥 Pull update (di Termux):"
echo "   cd ~/${REPO_NAME}"
echo "   git pull"
echo "   pkill -f 'python.*bot.py' && python bot.py"
echo ""
