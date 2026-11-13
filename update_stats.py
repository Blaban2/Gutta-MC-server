"""Henter spillerstatistikk fra Apex Hosting via FTP og lager site/stats.json."""
import ftplib, io, json, os, sys, urllib.request

HOST = os.environ["FTP_HOST"]
USER = os.environ["FTP_USER"]
PASS = os.environ["FTP_PASS"]
PORT = int(os.environ.get("FTP_PORT", "21"))
WORLD = os.environ.get("WORLD_DIR", "world")


def connect():
    try:  # prøv kryptert FTP først
        ftp = ftplib.FTP_TLS()
        ftp.connect(HOST, PORT, timeout=30)
        ftp.login(USER, PASS)
        ftp.prot_p()
        return ftp
    except Exception:
        ftp = ftplib.FTP()
        ftp.connect(HOST, PORT, timeout=30)
        ftp.login(USER, PASS)
        return ftp


def read(ftp, path):
    buf = io.BytesIO()
    ftp.retrbinary("RETR " + path, buf.write)
    return buf.getvalue()


def list_names(ftp, folder):
    try:
        return [n.split("/")[-1] for n in ftp.nlst(folder)]
    except ftplib.error_perm:
        return []


def uuid_names(ftp):
    names = {}
    for f in ("usercache.json", "whitelist.json"):
        try:
            for e in json.loads(read(ftp, f)):
                names[e["uuid"].lower()] = e["name"]
        except Exception:
            pass
    return names


def mojang_name(uuid):
    url = "https://sessionserver.mojang.com/session/minecraft/profile/" + uuid.replace("-", "")
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.load(r)["name"]
    except Exception:
        return None


ftp = connect()
names = uuid_names(ftp)

whitelist = []
try:
    whitelist = [e["name"] for e in json.loads(read(ftp, "whitelist.json"))]
except Exception:
    print("Kunne ikke lese whitelist.json")

stats_dir, files = None, []
for folder in (WORLD + "/players/stats", WORLD + "/stats"):
    files = [n for n in list_names(ftp, folder) if n.endswith(".json")]
    if files:
        stats_dir = folder
        break
if not files:
    print("Fant ingen stats-filer ennå. Sjekk WORLD_DIR hvis dette ikke stemmer (nå: %s)." % WORLD)

out = {}
for fn in files:
    uuid = fn[:-5].lower()
    stats = json.loads(read(ftp, stats_dir + "/" + fn)).get("stats", {})
    c = stats.get("minecraft:custom", {})
    ticks = c.get("minecraft:play_time", c.get("minecraft:play_one_minute", 0))
    cm = sum(c.get(k, 0) for k in (
        "minecraft:walk_one_cm", "minecraft:sprint_one_cm", "minecraft:crouch_one_cm"))
    name = names.get(uuid) or mojang_name(uuid) or uuid[:8]
    out[name] = {
        "hours": round(ticks / 72000, 1),
        "deaths": c.get("minecraft:deaths", 0),
        "mobKills": c.get("minecraft:mob_kills", 0),
        "km": round(cm / 100000, 1),
    }
ftp.quit()

os.makedirs("site", exist_ok=True)
with open("site/stats.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("Skrev stats for %d spillere fra %s" % (len(out), stats_dir))

if whitelist:
    with open("site/players.json", "w", encoding="utf-8") as f:
        json.dump(whitelist, f, ensure_ascii=False, indent=2)
    print("Skrev %d spillere fra whitelist" % len(whitelist))
