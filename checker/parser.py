import json
import re
import urllib.parse

COOKIE_KEYS = ("NetflixId", "SecureNetflixId", "nfvdid")
# Alternation harus key terpanjang dulu, supaya "SecureNetflixId" tidak
# tertangkap sebagian sebagai "NetflixId".
_KEY_ALT = "|".join(sorted(COOKIE_KEYS, key=len, reverse=True))
_KEY_SET = set(COOKIE_KEYS)

# name=value pasangan cookie (nilai boleh mengandung '=' untuk padding base64)
_PAIR_RE = re.compile(rf"(?<!\w)({_KEY_ALT})\s*=\s*([^;\s]+)")


def decode_cookie_value(v):
    if isinstance(v, str) and "%" in v:
        try:
            return urllib.parse.unquote(v)
        except Exception:
            return v
    return v


def _group_pairs(pairs):
    """Gabungkan pasangan (name, value) jadi daftar akun.

    Akun baru dimulai saat sebuah key muncul lagi — ini menangani
    "1 akun per baris", "1 cookie per baris", maupun blok dipisah baris kosong.
    """
    accounts = []
    cur = {}
    for k, v in pairs:
        if k not in _KEY_SET:
            continue
        if k in cur:
            # key berulang => akun baru
            if cur.get("NetflixId"):
                accounts.append(cur)
            cur = {}
        cur[k] = decode_cookie_value(v)
    if cur.get("NetflixId"):
        accounts.append(cur)
    return accounts


def parse_netscape(content: str):
    """Netscape format -> satu dict gabungan (kompatibilitas single akun)."""
    cookies = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            name = parts[5]
            val = parts[6]
            if name in _KEY_SET:
                cookies[name] = decode_cookie_value(val)
    return cookies


def parse_netscape_multi(content: str):
    """Netscape format -> daftar akun (multi akun dalam satu file)."""
    pairs = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            name, val = parts[5], parts[6]
        elif len(parts) == 2:
            name, val = parts[0], parts[1]
        else:
            continue
        if name in _KEY_SET:
            pairs.append((name, val))
    return _group_pairs(pairs)


def parse_json(content: str):
    """JSON -> satu dict gabungan (kompatibilitas single akun)."""
    try:
        data = json.loads(content)
    except Exception:
        return {}
    if isinstance(data, list):
        cookies = {}
        for c in data:
            if not isinstance(c, dict):
                continue
            n = c.get("name")
            v = c.get("value")
            if n in _KEY_SET and isinstance(v, str):
                cookies[n] = decode_cookie_value(v)
        return cookies
    if isinstance(data, dict):
        if any(k in data for k in _KEY_SET):
            return {
                k: decode_cookie_value(v)
                for k, v in data.items()
                if k in _KEY_SET and isinstance(v, str)
            }
        if isinstance(data.get("cookies"), list):
            return parse_json(json.dumps(data["cookies"]))
    return {}


def parse_raw(content: str):
    cookies = {}
    for m in _PAIR_RE.finditer(content):
        cookies[m.group(1)] = decode_cookie_value(m.group(2))
    return cookies


def _is_namevalue_list(data):
    """True kalau list berisi objek {"name": <cookie key>, "value": ...}."""
    if not isinstance(data, list) or not data:
        return False
    if not all(isinstance(x, dict) for x in data):
        return False
    names = {x.get("name") for x in data}
    return bool(names & _KEY_SET)


def _collect_from_json(data):
    """JSON apa pun (objek/array/nested) -> daftar akun."""
    if isinstance(data, list):
        # array of {"name":..., "value":...} => bisa banyak akun (JSONL-style)
        if _is_namevalue_list(data):
            pairs = [
                (x.get("name"), x.get("value"))
                for x in data
                if isinstance(x.get("value"), str)
            ]
            return _group_pairs(pairs)
        # array of account dicts (atau campuran) => rekursif
        out = []
        for item in data:
            out.extend(_collect_from_json(item))
        return out

    if isinstance(data, dict):
        # dict akun langsung: {"NetflixId":..,"SecureNetflixId":..}
        d = {
            k: decode_cookie_value(v)
            for k, v in data.items()
            if k in _KEY_SET and isinstance(v, str)
        }
        if d.get("NetflixId"):
            return [d]
        # nested list
        for key in ("cookies", "accounts", "items", "results", "data"):
            if isinstance(data.get(key), list):
                got = _collect_from_json(data[key])
                if got:
                    return got
        # satu objek name/value
        n = data.get("name")
        v = data.get("value")
        if n in _KEY_SET and isinstance(v, str):
            return _group_pairs([(n, v)])
        return []

    return []


def extract_cookies_dict(text: str):
    """Ambil satu akun gabungan (fallback)."""
    for fn in (parse_json, parse_netscape, parse_raw):
        d = fn(text)
        if d.get("NetflixId"):
            return d
    return parse_raw(text)


def cookie_dict_to_header(d: dict):
    # only send NetflixId + SecureNetflixId (+ nfvdid if present)
    parts = []
    for k in COOKIE_KEYS:
        if k in d:
            parts.append(f"{k}={d[k]}")
    return "; ".join(parts)


def parse_bulk_text(text: str):
    """Return list of cookie dicts dari input apa pun.

    Didukung: JSON (objek/array/nested), JSONL, Netscape (multi akun),
    raw `Key=value;` (1 akun per baris ATAU 1 cookie per baris),
    dan Cookie header.
    """
    text = (text or "").strip()
    if not text:
        return []

    # 1) JSON utuh
    try:
        data = json.loads(text)
    except Exception:
        data = None
    if data is not None:
        got = _collect_from_json(data)
        if got:
            return got

    # 2) JSONL / beberapa objek JSON dipisah newline
    if text.lstrip().startswith(("{", "[")):
        objs = []
        for line in text.splitlines():
            s = line.strip().rstrip(",")
            if not s or s in ("[", "]"):
                continue
            try:
                objs.append(json.loads(s))
            except Exception:
                objs = []
                break
        if objs:
            got = _collect_from_json(objs)
            if got:
                return got

    # 3) Netscape (tab-separated)
    if "\t" in text:
        got = parse_netscape_multi(text)
        if got:
            return got

    # 4) raw Key=value (multi akun / multi baris)
    pairs = _PAIR_RE.findall(text)
    if pairs:
        got = _group_pairs(pairs)
        if got:
            return got

    # 5) fallback terakhir
    d = extract_cookies_dict(text)
    if d.get("NetflixId"):
        return [d]
    return []


def netscape_from_dict(d: dict):
    lines = []
    for k in COOKIE_KEYS:
        if k in d:
            lines.append(f".netflix.com\tTRUE\t/\tTRUE\t0\t{k}\t{d[k]}")
    return "\n".join(lines)
