# 🛑 Cara Stop Bot

## Opsi 1: Stop dengan pkill (paling mudah)
```bash
pkill -f "python.*bot.py"
```

## Opsi 2: Cari PID lalu kill manual
```bash
# Cari process ID bot
ps aux | grep "python.*bot.py" | grep -v grep

# Kill dengan PID (ganti 12345 dengan PID yang muncul)
kill 12345

# Kalau tidak mau stop, paksa kill:
kill -9 12345
```

## Opsi 3: CTRL+C (kalau bot jalan foreground)
Tekan `CTRL + C` di terminal yang jalanin bot

---

## ✅ Cara Jalankan Ulang Bot
```bash
cd /workspace/nimble-darwin
python3 bot.py
```

Bot akan jalan di **polling mode** dan set BotCommands otomatis.
