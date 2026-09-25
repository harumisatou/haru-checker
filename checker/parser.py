import json
import re
import urllib.parse

COOKIE_KEYS = ("NetflixId", "SecureNetflixId", "nfvdid")

def decode_cookie_value(v):
    if isinstance(v, str) and "%" in v:
        try:
            return urllib.parse.unquote(v)
        except Exception:
            return v
    return v

def parse_netscape(content: str):
    cookies = {}
    for line in content.splitlines():
        line=line.strip()
        if not line or line.startswith("#"):
            continue
        parts=line.split("\t")
        if len(parts) >= 7:
            name=parts[5]
            val=parts[6]
            if name in COOKIE_KEYS:
                cookies[name]=decode_cookie_value(val)
        elif len(parts) >= 2:
            # fallback single line Netscape-ish
            pass
    return cookies

def parse_json(content: str):
    cookies={}
    try:
        data=json.loads(content)
    except:
        return {}
    if isinstance(data, list):
        for c in data:
            n=c.get("name")
            v=c.get("value")
            if n in COOKIE_KEYS and isinstance(v,str):
                cookies[n]=decode_cookie_value(v)
    elif isinstance(data, dict):
        # dict of cookie name->value or with cookies list
        if any(k in data for k in COOKIE_KEYS):
            for k in COOKIE_KEYS:
                v=data.get(k)
                if isinstance(v,str):
                    cookies[k]=decode_cookie_value(v)
        elif isinstance(data.get("cookies"), list):
            for c in data["cookies"]:
                n=c.get("name")
                v=c.get("value")
                if n in COOKIE_KEYS and isinstance(v,str):
                    cookies[n]=decode_cookie_value(v)
    return cookies

def parse_raw(content: str):
    cookies={}
    for k in COOKIE_KEYS:
        m=re.search(rf"(?<!\w){re.escape(k)}\=([^;\s]+)", content)
        if m:
            cookies[k]=decode_cookie_value(m.group(1))
    return cookies

def extract_cookies_dict(text: str):
    # try json -> netscape -> raw
    for fn in (parse_json, parse_netscape, parse_raw):
        d=fn(text)
        if d.get("NetflixId"):
            return d
    # if none, try raw anyway
    d=parse_raw(text)
    return d

def cookie_dict_to_header(d: dict):
    # only send NetflixId + SecureNetflixId (+ nfvdid if present)
    parts=[]
    for k in COOKIE_KEYS:
        if k in d:
            parts.append(f"{k}={d[k]}")
    return "; ".join(parts)

def parse_bulk_text(text: str):
    """Return list of cookie dicts from bulk input text.
    - if text contains json array -> single
    - if netscape file -> single per file (but caller handles file)
    - if multiple raw lines each with NetflixId -> each line is one account
    """
    text=text.strip()
    if not text:
        return []
    # Try JSON single
    try:
        data=json.loads(text)
        if isinstance(data, list) and any(isinstance(x,dict) and "name" in x for x in data):
            d=parse_json(text)
            if d.get("NetflixId"):
                return [d]
    except:
        pass
    # If contains Netscape header
    if ".netflix.com" in text and "\t" in text:
        d=parse_netscape(text)
        if d.get("NetflixId"):
            return [d]
    # else split by lines, each line raw cookie
    lines=[l.strip() for l in text.splitlines() if l.strip()]
    # If single line contains NetflixId but also multiple accounts separated by newline without header, handle
    if len(lines)==1 and "NetflixId" in lines[0]:
        # could be single account with multiple cookies separated by ; or\n
        d=parse_raw(lines[0])
        if d.get("NetflixId"):
            return [d]
    result=[]
    for line in lines:
        if "NetflixId" not in line:
            continue
        d=parse_raw(line)
        if d.get("NetflixId"):
            result.append(d)
        # also try netscape single line?
    if result:
        return result
    # fallback: whole text as one
    d=extract_cookies_dict(text)
    if d.get("NetflixId"):
        return [d]
    return []

def netscape_from_dict(d: dict):
    lines=[]
    for k in COOKIE_KEYS:
        if k in d:
            lines.append(f".netflix.com\tTRUE\t/\tTRUE\t0\t{k}\t{d[k]}")
    return "\n".join(lines)
