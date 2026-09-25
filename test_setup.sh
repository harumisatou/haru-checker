#!/bin/bash
# Script tes setup lokal HARU CHECKER

echo "=================================================="
echo "TES SETUP LOKAL HARU CHECKER"
echo "=================================================="

# 1. Cek Python
echo -e "\n[1/5] Cek Python version..."
python3 --version || { echo "❌ Python3 tidak ditemukan"; exit 1; }

# 2. Cek dependencies
echo -e "\n[2/5] Cek dependencies..."
MISSING=""
python3 -c "import telegram" 2>/dev/null || MISSING="$MISSING python-telegram-bot"
python3 -c "import requests" 2>/dev/null || MISSING="$MISSING requests"
python3 -c "import bs4" 2>/dev/null || MISSING="$MISSING beautifulsoup4"
python3 -c "import dotenv" 2>/dev/null || MISSING="$MISSING python-dotenv"

if [ -n "$MISSING" ]; then
    echo "❌ Dependencies belum lengkap:$MISSING"
    echo "   Jalankan: pip3 install python-telegram-bot requests beautifulsoup4 python-dotenv"
    exit 1
fi
echo "✅ Dependencies OK"

# 3. Cek syntax semua modul
echo -e "\n[3/5] Cek syntax Python..."
python3 -m py_compile bot.py config.py checker/*.py utils/*.py 2>/dev/null || {
    echo "❌ Syntax error di modul"
    exit 1
}
echo "✅ Syntax OK"

# 4. Cek config file
echo -e "\n[4/5] Cek .env config..."
if [ ! -f .env ]; then
    echo "⚠️  File .env belum ada"
    echo "   Jalankan: cp .env.example .env"
    echo "   Lalu edit .env dan isi BOT_TOKEN"
else
    if grep -q "BOT_TOKEN=your_bot_token_here" .env 2>/dev/null || ! grep -q "BOT_TOKEN=" .env 2>/dev/null; then
        echo "⚠️  BOT_TOKEN di .env belum diisi"
        echo "   Cara dapat token:"
        echo "   1. Chat @BotFather di Telegram"
        echo "   2. Ketik /newbot"
        echo "   3. Copy token lalu paste ke .env"
    else
        echo "✅ BOT_TOKEN configured"
    fi
fi

# 5. Test import checker
echo -e "\n[5/5] Tes import modul checker..."
python3 -c "from checker.netflix import check_one_cookie; from checker.parser import *; print('✅ Import checker OK')" || {
    echo "❌ Import error"
    exit 1
}

echo -e "\n=================================================="
echo "✅ SETUP LOLOS — Bot siap dijalankan!"
echo "=================================================="
echo -e "\nCara jalankan:"
echo "  python3 bot.py"
echo ""
echo "Setelah bot jalan, buka bot di Telegram:"
echo "  /start    → lihat menu"
echo "  /myid     → cek user ID"
echo "  /help     → panduan lengkap"
echo ""
echo "Kirim cookie untuk tes checker:"
echo "  NetflixId=xxx; SecureNetflixId=yyy;"
