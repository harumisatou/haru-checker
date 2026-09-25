import re
import html
import json
import unicodedata
import requests
from .nftoken import create_nftoken

# ---------- decode helper (copied from main.py) ----------
def decode_netflix_value(value):
    if value is None:
        return None
    cleaned = html.unescape(str(value))
    replacements = {
        "\\x20": " ",
        "\\u00A0": " ",
        "\\u00a0": " ",
        "&nbsp;": " ",
        "u00A0": " ",
    }
    for s,t in replacements.items():
        cleaned=cleaned.replace(s,t)
    cleaned=cleaned.replace("\\/", "/").replace('\\"', '"').replace("\\n", " ").replace("\\t", " ")
    def _du(m):
        try: return chr(int(m.group(1),16))
        except: return m.group(0)
    def _dx(m):
        try: return chr(int(m.group(1),16))
        except: return m.group(0)
    for _ in range(3):
        prev=cleaned
        cleaned=re.sub(r"\\u([0-9a-fA-F]{4})", _du, cleaned)
        cleaned=re.sub(r"\\x([0-9a-fA-F]{2})", _dx, cleaned)
        cleaned=re.sub(r"(?<!\\)\bu([0-9a-fA-F]{4})(?![0-9a-fA-F])", _du, cleaned)
        cleaned=cleaned.replace("\\\\", "\\")
        if cleaned==prev:
            break
    cleaned=re.sub(r"(?<=[A-Za-z])\s+(?=[^\x00-\x7F])", "", cleaned)
    cleaned=re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None

def extract_first_match(text, patterns, flags=0):
    for pat in patterns:
        m=re.search(pat, text, flags)
        if m:
            return decode_netflix_value(m.group(1))
    return None

def extract_bool_value(text, patterns):
    v=extract_first_match(text, patterns, re.IGNORECASE)
    if v is None:
        return None
    low=v.strip().lower()
    if low in ("true","yes","1","on"): return "Yes"
    if low in ("false","no","0","off"): return "No"
    return v

def normalize_plan_key(plan_name):
    if not plan_name:
        return "unknown"
    simplified=unicodedata.normalize("NFKD", plan_name)
    simplified="".join(ch for ch in simplified if not unicodedata.combining(ch))
    simplified=re.sub(r"[^a-zA-Z0-9]+","_", simplified).strip("_").lower()
    return simplified or "unknown"

def norm_token(value):
    """Normalisasi longgar untuk perbandingan status.

    "currentMember" / "current_member" / "CURRENT MEMBER" -> "currentmember".
    Dipakai karena normalize_plan_key() menyisipkan "_" untuk camelCase,
    sehingga perbandingan "current_member" tidak pernah cocok.
    """
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

# Pemetaan jumlah stream Netflix -> tier plan (Basic 1, Standard 2, Premium 4)
_STREAM_PLANS = {1: "Basic", 2: "Standard", 4: "Premium"}

def plan_label(info):
    """Label plan yang tahan banting, dipakai bot & formatter.

    Urutan: localizedPlanName -> maxStreams -> videoQuality -> planPrice.
    """
    info = info or {}
    name = decode_netflix_value(info.get("localizedPlanName"))
    if name:
        return name

    ms = info.get("maxStreams")
    if ms is not None:
        try:
            n = int(str(ms).strip())
            if n in _STREAM_PLANS:
                suffix = "stream" if n == 1 else "streams"
                return f"{_STREAM_PLANS[n]} ({n} {suffix})"
            if n > 0:
                return f"Unknown ({n} streams)"
        except Exception:
            pass

    quality = (info.get("videoQuality") or "").upper()
    if "UHD" in quality or "4K" in quality:
        return "Premium"
    if "HD" in quality:
        return "Standard"
    if "SD" in quality:
        return "Basic"

    price = decode_netflix_value(info.get("planPrice"))
    if price:
        return price
    return "Unknown"

def format_plan_label(plan_key):
    if not plan_key: return "Unknown"
    return plan_key.replace("_"," ").title()

def derive_plan_info(info, is_subscribed):
    raw_plan = decode_netflix_value(info.get("localizedPlanName"))
    if not is_subscribed and not raw_plan:
        return "free","Free"
    normalized = normalize_plan_key(raw_plan) if raw_plan else ""
    plan_aliases={
        "premium": ["premium","premium_plan","cao_cap_plan","ultra","platinum","4k","uhd"],
        "standard": ["standard","standar","estandar","padrao"],
        "standard_with_ads": ["standard_with_ads","standard_with_advertising","con_anuncios","com_anuncios"],
        "basic": ["basic","basico","basico","essencial"],
        "mobile": ["mobile","movil","celular"],
    }
    for canonical, aliases in plan_aliases.items():
        if any(a in normalized for a in aliases):
            # try to restore proper label from raw if possible
            label_map={"premium":"Premium","standard":"Standard","standard_with_ads":"Standard With Ads","basic":"Basic","mobile":"Mobile"}
            return canonical, label_map.get(canonical, raw_plan or canonical)
    if raw_plan:
        return normalize_plan_key(raw_plan), raw_plan
    return "unknown","Unknown"

def is_subscribed_account(info):
    """True kalau akun benar-benar member aktif.

    Tidak lagi menggantungkan diri pada perbandingan string yang salah
    ("currentMember" tidak pernah == "current_member"), dan bukti sesi
    anonim (ANONYMOUS) tidak dianggap valid.
    """
    info = info or {}
    status = norm_token(info.get("membershipStatus"))
    if status == "currentmember":
        return True
    if status == "anonymous":
        # Halaman login/tanpa sesi -> cookie tidak valid, apa pun isi field lain.
        return False
    # Tanpa status yang jelas: anggap berlangganan hanya kalau ada nama plan nyata.
    return bool(info.get("localizedPlanName"))

def is_on_hold_account(info):
    info = info or {}
    hold=info.get("holdStatus")
    if hold:
        low=str(hold).strip().lower()
        if low=="yes": return True
        if low=="no": return False
    status=norm_token(info.get("membershipStatus"))
    return any(tok in status for tok in ("hold","pastdue","paymentretry","paused","suspend"))

def extract_info(response_text):
    # try graphql payload first
    try:
        payload=json.loads(response_text)
        if isinstance(payload,dict) and "data" in payload:
            data=payload.get("data") or {}
            growth=data.get("growthAccount") or {}
            curr=data.get("currentProfile") or {}
            # simplified: if payload has growthAccount, use it
            if growth:
                email=None
                # email from curr profile
                ge=(curr.get("growthEmail") or {})
                eo=(ge.get("email") or {})
                email=eo.get("value") if isinstance(eo,dict) else None
                plan=(growth.get("currentPlan") or {}).get("plan") or {}
                info={
                    "email": decode_netflix_value(email),
                    "countryOfSignup": decode_netflix_value(((growth.get("countryOfSignUp") or {}).get("code"))),
                    "memberSince": decode_netflix_value(growth.get("memberSince")),
                    "nextBillingDate": decode_netflix_value(((growth.get("nextBillingDate") or {}).get("localDate"))),
                    "membershipStatus": decode_netflix_value(growth.get("membershipStatus")),
                    "localizedPlanName": decode_netflix_value(plan.get("name")),
                    "planPrice": decode_netflix_value(((plan.get("price") or {}).get("displayValue")) or plan.get("priceDisplay")),
                    "holdStatus": "Yes" if growth.get("isUserOnHold") else None,
                }
                # filter None
                info={k:v for k,v in info.items() if v}
                if info.get("email") or info.get("localizedPlanName"):
                    return info
    except:
        pass
    # regex fallback (like main.py)
    extracted={
        "accountOwnerName": extract_first_match(response_text, [r'"accountOwnerName"\s*:\s*"([^"]+)"', r'"ownerName"\s*:\s*"([^"]+)"', r'"profileName"\s*:\s*"([^"]+)"']),
        "email": extract_first_match(response_text, [r'"emailAddress"\s*:\s*"([^"]+)"', r'"email"\s*:\s*"([^"]+)"']),
        "countryOfSignup": extract_first_match(response_text, [r'"currentCountry"\s*:\s*"([^"]+)"', r'"countryOfSignup":\s*"([^"]+)"', r'"countryOfSignUp"[^"]*"code"\s*:\s*"([^"]+)"']),
        "memberSince": extract_first_match(response_text, [r'"memberSince":\s*"([^"]+)"']),
        "nextBillingDate": extract_first_match(response_text, [r'"nextBillingDate"\s*:\s*"([^"]+)"', r'"nextBilling"\s*:[^}]*"value"\s*:\s*"([^"]+)"']),
        "userGuid": extract_first_match(response_text, [r'"userGuid":\s*"([^"]+)"']),
        "membershipStatus": extract_first_match(response_text, [r'"membershipStatus"\s*:\s*"([^"]+)"']),
        "localizedPlanName": extract_first_match(response_text, [r'"localizedPlanName"\s*:\s*"([^"]+)"', r'"currentPlan"[^}]*"name"\s*:\s*"([^"]+)"', r'"planName"\s*:\s*"([^"]+)"']),
        "planPrice": extract_first_match(response_text, [r'"formattedPlanPrice"\s*:\s*"([^"]+)"', r'"planPriceDisplay"\s*:\s*"([^"]+)"']),
        "holdStatus": extract_bool_value(response_text, [r'"holdStatus"\s*:\s*(true|false)', r'"isUserOnHold"\s*:\s*(true|false)', r'"isOnHold"\s*:\s*(true|false)']),
        "paymentMethodType": extract_first_match(response_text, [r'"paymentMethodType"\s*:\s*"([^"]+)"']),
        "videoQuality": extract_first_match(response_text, [r'"videoQuality"\s*:\s*"([^"]+)"']),
        "maxStreams": extract_first_match(response_text, [r'"maxStreams"\s*:\s*"([^"]+)"', r'"maxStreams"\s*:\s*(\d+)']),
        "phoneNumber": extract_first_match(response_text, [r'"phoneNumber"\s*:\s*"([^"]+)"']),
    }
    # clean None empty
    extracted={k:v for k,v in extracted.items() if v not in (None,"","null")}
    # fix hold default
    if extracted.get("holdStatus") is None and extracted.get("membershipStatus"):
        ms=norm_token(extracted["membershipStatus"])
        if any(tok in ms for tok in ("hold","pastdue","paymentretry","paused","suspend")):
            extracted["holdStatus"]="Yes"
        elif ms=="currentmember":
            extracted["holdStatus"]="No"
    return extracted

def has_complete(info):
    return bool(info and (info.get("email") or info.get("localizedPlanName") or info.get("membershipStatus")))

def check_one_cookie(cookie_dict, timeout=15, generate_nftoken=True):
    """Return dict: status=valid/hold/invalid, info, nftoken, error"""
    header_cookie = "; ".join([f"{k}={v}" for k,v in cookie_dict.items() if k in ("NetflixId","SecureNetflixId","nfvdid")])
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    session=requests.Session()
    session.headers.update(headers)
    # cookie header manually
    session.cookies.clear()
    # use requests cookie jar
    for k,v in cookie_dict.items():
        session.cookies.set(k, v, domain=".netflix.com", path="/")
    try:
        r=session.get("https://www.netflix.com/account/membership", timeout=timeout, allow_redirects=True)
        text=r.text or ""
        # check invalid conditions
        if r.status_code in (401,403) or "SignIn" in r.url or "login" in r.url.lower():
            # try YourAccount fallback quickly
            if "memberSince" not in text and "membershipStatus" not in text:
                return {"status":"invalid","info":None,"nftoken":None,"error":f"http {r.status_code} redirect to login"}
        # extract info
        info=extract_info(text)
        # if not complete, try YourAccount page
        if not has_complete(info):
            try:
                r2=session.get("https://www.netflix.com/YourAccount", timeout=timeout)
                info2=extract_info(r2.text)
                # merge
                for k,v in info2.items():
                    if k not in info or not info[k]:
                        info[k]=v
            except:
                pass
        if not info or not has_complete(info):
            # Sesi mungkin aktif tapi info tidak lengkap. Jangan difabrikasi
            # sebagai "current_member" hanya karena halaman mengandung "Browse"
            # — itu bikin cookie invalid lolos sebagai valid.
            if "Currently Watching" in text or "Browse" in text or "membershipStatus" in text:
                info=info or {}
                info.setdefault("holdStatus", "Yes")
                return {"status":"hold","info":info,"nftoken":None,"error":"session active, info incomplete"}
            else:
                # maybe invalid
                if "Incorrect password" in text or "We couldn't find" in text or len(text)<2000:
                    return {"status":"invalid","info":info,"nftoken":None,"error":"invalid/expired"}
                # fallback: if no info extracted but status 200 and not login, consider invalid
                if not info:
                    return {"status":"invalid","info":None,"nftoken":None,"error":"no account info"}
        # determine subscribed
        # Anonim = halaman login/sign-in, bukan sesi nyata -> invalid
        if norm_token(info.get("membershipStatus")) == "anonymous":
            return {"status":"invalid","info":info,"nftoken":None,"error":"anonymous/not logged in"}

        subscribed=is_subscribed_account(info)
        if not subscribed:
            # beberapa halaman memberi nama plan tapi bukan langganan aktif
            return {"status":"invalid","info":info,"nftoken":None,"error":"free/no subscription"}
        on_hold=is_on_hold_account(info)
        if on_hold:
            status="hold"
        else:
            status="valid"
        nftoken_data=None
        if generate_nftoken and status in ("valid","hold"):
            nft,err=create_nftoken(cookie_dict, timeout=timeout)
            if nft:
                nftoken_data=nft
        return {"status":status,"info":info,"nftoken":nftoken_data,"error":None}
    except requests.exceptions.Timeout:
        return {"status":"invalid","info":None,"nftoken":None,"error":"timeout"}
    except Exception as e:
        return {"status":"invalid","info":None,"nftoken":None,"error":str(e)[:120]}
