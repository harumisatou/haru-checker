import os
import requests

# Auto-renew FPS.ms free server (24h) biar gak Expired
# Pakai API Key ptlc_xxx dari Secrets / env FPS_API_KEY
API_KEY = os.getenv("FPS_API_KEY") or os.getenv("FPS_API_TOKEN") or "ptlc_c3PghdoLTQTNpHaE4khfY7Y47aGVpyI9d4UvUaXkSxo"
BASE = "https://panel.fps.ms"

def api_get(path):
    r = requests.get(f"{BASE}{path}", headers={"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}, timeout=15)
    return r

def api_post(path):
    r = requests.post(f"{BASE}{path}", headers={"Authorization": f"Bearer {API_KEY}", "Accept": "application/json", "Content-Type": "application/json"}, timeout=15, json={})
    return r

def main():
    print("=== FPS.ms Auto Renew ===")
    # Cek account
    r = api_get("/api/client/account")
    print(f"Account: {r.status_code} {r.text[:200]}")
    # List servers via /api/client (yang work tadi)
    r = api_get("/api/client")
    data = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
    servers = data.get("data", []) if isinstance(data, dict) else []
    print(f"Found {len(servers)} servers")
    if not servers:
        print("Belum ada server. Deploy dulu: panel.fps.ms -> Deploy Server -> Telegram Bot Python")
        return
    for s in servers:
        attrs = s.get("attributes", s)
        sid = attrs.get("identifier") or attrs.get("id") or attrs.get("uuid")
        name = attrs.get("name") or attrs.get("description") or sid
        print(f"- Server {name} ({sid})")
        ep = f"/api/client/servers/{sid}/billing/renew"
        try:
            rr = api_post(ep)
            print(f"  POST {ep} -> {rr.status_code} {rr.text[:300]}")
            if rr.status_code in (200, 201, 204):
                print(f"  ✅ Renew sukses!")
            else:
                print(f"  ❌ Renew gagal")
        except Exception as e:
            print(f"  err {ep}: {e}")

if __name__ == "__main__":
    main()
