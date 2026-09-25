# 🤖 HARU CHECKER - Netflix Cookie Checker Bot

Bot Telegram canggih untuk mengecek validitas cookies Netflix dengan fitur bulk checking, multi-format support, dan output lengkap.

## ✨ Fitur Utama

- ✅ **Multi-Format Support**: Raw cookies, Netscape, JSON, ZIP files
- ⚡ **Bulk Checking**: Support hingga 10,000 cookies per request
- 🎯 **Smart Confirmation**: Auto-detect bulk & tanya jumlah cookies yang mau di-cek
- 📊 **Output Lengkap**: Valid accounts only dengan detail plan & country
- 🔗 **3 Login Buttons**: PC, Mobile, dan TV (Smart TV support)
- 🚀 **Real-time Progress**: Progress notification setiap 50 cards
- 🛡️ **Production Ready**: Error handler, health monitoring, owner commands

## 📦 Instalasi

### Requirements

- Python 3.8+
- pip dependencies (lihat `requirements.txt`)

### Setup

1. **Clone repository**
```bash
git clone https://github.com/YOUR_USERNAME/haru-checker.git
cd haru-checker
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Setup environment**
```bash
cp .env.example .env
nano .env  # Isi BOT_TOKEN dari @BotFather
```

4. **Jalankan bot**
```bash
python bot.py
```

## 🎮 Command List

| Command | Deskripsi |
|---------|-----------|
| `/start` | Menu utama bot |
| `/ping` | Cek response time & status bot |
| `/myid` | Lihat ID Telegram & role kamu |
| `/bulk` | Mode scan massal |
| `/basic` | Tampilan ringkas (cards only) |
| `/fullinfo` | Tampilan detail lengkap |
| `/mode` | Ganti mode output |
| `/filter` | Filter paket (Premium/Standard) |
| `/country` | Filter negara |
| `/help` | Panduan lengkap |
| `/stopbot` | Stop bot (Owner only) |

## 📤 Format Input

Bot support berbagai format cookies:

**1. Direct Paste (Raw)**
```
NetflixId=xxx; SecureNetflixId=yyy;
```

**2. Netscape Format**
```
.netflix.com	TRUE	/	FALSE	0	NetflixId	xxx
.netflix.com	TRUE	/	FALSE	0	SecureNetflixId	yyy
```

**3. JSON Format**
```json
[
  {"name": "NetflixId", "value": "xxx"},
  {"name": "SecureNetflixId", "value": "yyy"}
]
```

**4. File Upload**
- `.txt` file (bulk cookies)
- `.json` file
- `.zip` file berisi multiple files

## 📊 Output Format

Bot akan kirim:

1. **Valid Cards** (satu per satu, delay 1 detik)
   - Email / Phone
   - Country
   - Plan (Premium/Standard)
   - 3 tombol: 🖥 PC, 📱 Mobile, 📺 TV

2. **Summary Counter**
   - Total checked
   - Valid / Hold / Invalid count

3. **File Download** (untuk bulk)
   - `valid_accounts.txt` - semua akun valid
   - `Hits.zip` - lengkap dengan NFToken

## 🔧 Configuration

Edit `.env` untuk konfigurasi:

```env
BOT_TOKEN=your_bot_token_here
MAX_COOKIES_PER_REQUEST=10000
MAX_CONCURRENCY=10
REQUEST_TIMEOUT=15
PORT=8000
ADMIN_ID=your_telegram_user_id
```

## 🚀 Deployment

### VPS (Recommended)

1. **Setup systemd service** (Ubuntu/Debian)
```bash
sudo nano /etc/systemd/system/haru-checker.service
```

```ini
[Unit]
Description=Haru Checker Bot
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/haru-checker
ExecStart=/usr/bin/python3 bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable haru-checker
sudo systemctl start haru-checker
```

2. **Check status**
```bash
sudo systemctl status haru-checker
```

### Termux (Android)

```bash
# Install dependencies
pkg update && pkg install python git
pip install -r requirements.txt

# Setup .env
cp .env.example .env
nano .env

# Run bot
nohup python bot.py > bot.log 2>&1 &
echo $! > bot.pid
```

**Stop bot:**
```bash
kill $(cat bot.pid)
```

## 🛠️ Development

### Project Structure

```
haru-checker/
├── bot.py              # Main bot logic
├── config.py           # Configuration & constants
├── checker/
│   ├── netflix.py      # Netflix API checker
│   ├── parser.py       # Multi-format parser
│   └── utils.py        # Helper functions
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
└── README.md          # This file
```

## 📝 License

MIT License - Feel free to use and modify

## 💬 Support

Untuk pertanyaan atau bug report, buka issue di GitHub atau contact @harumisatou di Telegram.

## 🙏 Credits

Developed with ❤️ for Netflix cookie checking community

---

⭐ Star repository ini jika berguna untuk kamu!
