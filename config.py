import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip().replace(" ", "").replace("\n","").replace("\r","")

# Support both ADMIN_ID (singular) and ADMIN_IDS (plural comma-separated)
admin_id_single = os.getenv("ADMIN_ID", "").strip()
admin_ids_multi = os.getenv("ADMIN_IDS", "").strip()

ADMIN_IDS = []
if admin_id_single.isdigit():
    ADMIN_IDS.append(int(admin_id_single))
if admin_ids_multi:
    ADMIN_IDS.extend([int(x) for x in admin_ids_multi.split(",") if x.strip().isdigit()])
# Samakan dengan limit aktual di bot.py (get_limit_for = 10000)
MAX_COOKIES_PER_REQUEST = int(os.getenv("MAX_COOKIES_PER_REQUEST", "10000"))
FREE_LIMIT = int(os.getenv("FREE_LIMIT", "10000"))  # limit teman/orang lain
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "10"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))
ENABLE_NVTOKEN = os.getenv("ENABLE_NVTOKEN", "true").lower() in ("1","true","yes")
PORT = int(os.getenv("PORT", "8000"))

# messages — professional style lengkap
WELCOME_MSG = """🎬 <b>HARU CHECKER — Netflix Cookie Checker</b>
────────────────────────
⚡ Capacity : ∞ Unlimited Checks | Bulk Supported
💎 Status : Active & Ready
────────────────────────
<b>📌 CARA PAKAI</b>
Kirim cookies Netflix dalam format apapun — bot akan cek <b>otomatis tanpa klik button</b>:
• 📋 Direct paste — <code>NetflixId=xxx; SecureNetflixId=xxx</code> (bisa banyak baris)
• 📄 File .txt — bulk (Netscape / JSON / raw)
• 📦 File .zip — bulk berisi banyak .txt/.json
📦 Support: Direct • Netscape • JSON
⚡ Limit: Up to <b>{max_cookies}</b> / request

────────────────────────
<b>📚 DAFTAR PERINTAH</b>
/start — Menu Utama
/ping — Cek Response Time & Status Bot
/bulk — Mode Scan Massal
/basic — Tampilan Ringkas
/fullinfo — Detail Lengkap
/mode — Ganti Mode Output
/filter — Filter Paket (Premium/Standard)
/country — Filter Negara
/help — Panduan Lengkap
/myid — Cek ID Telegram & Role
/stopbot — Stop Bot (Owner Only)

────────────────────────
<b>📤 OUTPUT</b>
✅ Valid — akun aktif + tombol login PC/Mobile/TV (nftoken)
📁 File: valid_accounts.txt • Hits.zip

🤖 Powered by @harumisatou
"""
HELP_MSG = """📖 <b>Help — How to use</b>

1. Kirim cookies Netflix dalam format apapun:
   - Paste langsung: <code>NetflixId=xxx; SecureNetflixId=xxx</code>
   - File .txt (1 cookie per baris atau Netscape)
   - File .zip berisi banyak .txt/.json

2. Bot akan cek otomatis dan kasih hasil:
   ✅ Valid (Active) — dikirim satu per satu tiap detik

3. Hasil file:
   • valid_accounts.txt
   • ZIP Premium Hits / Normal Hits + _SUMMARY.txt

4. Untuk akun Valid bot juga kirim <b>link auto-login (nftoken)</b> per akun dengan tombol PC, Mobile & TV biar bisa langsung login 1-klik.

5. Bulk check > 100 cookies: bot akan tanya mau cek berapa cookies.

⚠️ Limit: {max_cookies} cookies/request
"""
