from flask import Flask, jsonify, request, make_response, render_template
import re
import json
import os
import re

import time
import secrets
from datetime import datetime, timezone
from flask import abort
import os, json, secrets
from flask import Flask, jsonify, request, make_response, render_template, abort

app = Flask(__name__)

BANK_PATH = os.environ.get("BANK_PATH", "questions_bank.json")
ROUTES_DIR = os.environ.get("ROUTES_DIR", "routes")

COOKIE_NAME = "progress"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 Tage

TEAM_COOKIE = "team"
PLAYER_ID_COOKIE = "player_id"
PLAYER_NAME_COOKIE = "player_name"
PROGRESS_COOKIE = "progress"

COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 Tage

TEAM_FILES = {
    "team1": "team1.json",
    "team2": "team2.json",
    "team3": "team3.json",
    "team4": "team4.json",
}

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_bank():
    bank = load_json(BANK_PATH)
    if not isinstance(bank, list):
        raise ValueError("questions_bank.json must be a JSON array")

    by_title = {}
    dups = []
    for q in bank:
        t = (q or {}).get("title")
        if not t or not isinstance(t, str):
            raise ValueError("Each question must have a non-empty string 'title'")
        if t in by_title:
            dups.append(t)
        by_title[t] = q

    if dups:
        raise ValueError(f"Duplicate titles in bank: {dups}")

    return by_title

def load_route(team_key: str):
    filename = TEAM_FILES.get(team_key)
    if not filename:
        raise ValueError(f"Unknown team: {team_key}")

    path = os.path.join(ROUTES_DIR, filename)
    titles = load_json(path)

    if not isinstance(titles, list) or not all(isinstance(x, str) for x in titles):
        raise ValueError(f"{path} must be a JSON array of strings (titles)")

    return titles

BANK_BY_TITLE = load_bank()  # validiert Unique-Titles beim Start

ANIMAL_IDS = [
    "Fuchs", "Dachs", "Eule", "Igel", "Hase",
    "Bär", "Wolf", "Luchs", "Adler", "Gams",
    "Murmeltier", "Reh", "Hirsch", "Otter", "Biber",
    "Pinguin", "Panda", "Tiger", "Löwe", "Delfin"
]

assigned_animal_ids = set()  # welche Tiernamen schon vergeben sind

NUMBER_WORDS = {
    # deutsch
    "null": "0",
    "eins": "1",
    "ein": "1",
    "zwei": "2",
    "drei": "3",
    "vier": "4",
    "fünf": "5",
    "funf": "5",
    "sechs": "6",
    "sieben": "7",
    "acht": "8",
    "neun": "9",
    "zehn": "10",

    # englisch
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}

GM_KEY = os.environ.get("GM_KEY", "")  # optionaler Schutz

players = {}  # player_id -> {"first_seen":..., "last_seen":..., "progress": int, "user_agent": str}
attempts = [] # Liste von Attempts
# attempt: {"ts": "...", "player_id": "...", "q_index": int, "title": str, "answer": str, "correct": bool}

PLAYER_COOKIE = "player_id"
PLAYER_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 Tage

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def get_team(pid: str | None = None):
    # 1) Cookie
    t = request.cookies.get(TEAM_COOKIE)
    if t in TEAM_FILES:
        return t

    # 2) URL Param (override)
    t2 = request.args.get("team")
    if t2 in TEAM_FILES:
        return t2

    # 3) balanciert vergeben (least-used)
    # pid ist optional; wir brauchen ihn nur für Stabilität/Debug
    counts = {k: 0 for k in TEAM_FILES.keys()}
    for _pid, info in players.items():
        tt = info.get("team")
        if tt in counts:
            counts[tt] += 1

    # nimm das Team mit dem kleinsten count; bei Gleichstand: feste Reihenfolge team1..team4
    team = min(counts.keys(), key=lambda k: (counts[k], k))
    return team

def set_team_cookie(resp, team):
    resp.set_cookie(TEAM_COOKIE, team, max_age=COOKIE_MAX_AGE, samesite="Lax", secure=False)
    return resp

def get_player_id_and_name():
    pid = request.cookies.get(PLAYER_ID_COOKIE)
    pname = request.cookies.get(PLAYER_NAME_COOKIE)

    if pid and pname:
        return pid, pname

    # neue stabile ID
    pid = "p_" + secrets.token_urlsafe(8)

    # Tiername vergeben (freundlicher Anzeigename)
    for name in ANIMAL_IDS:
        if name not in assigned_animal_ids:
            assigned_animal_ids.add(name)
            pname = name
            break
    if not pname:
        pname = "Spieler-" + secrets.token_urlsafe(3)

    return pid, pname

def touch_player(pid: str, pname: str, progress: int | None = None):
    ua = request.headers.get("User-Agent", "")
    rec = players.get(pid) or {
        "player_name": pname,
        "first_seen": now_iso(),
        "last_seen": now_iso(),
        "progress": progress if progress is not None else 0,
        "user_agent": ua[:200],
    }
    rec["player_name"] = pname
    rec["last_seen"] = now_iso()
    rec["user_agent"] = ua[:200]
    if progress is not None:
        rec["progress"] = progress
    players[pid] = rec

def set_player_cookies(resp, pid: str, pname: str):
    resp.set_cookie(PLAYER_ID_COOKIE, pid, max_age=COOKIE_MAX_AGE, samesite="Lax", secure=False)
    resp.set_cookie(PLAYER_NAME_COOKIE, pname, max_age=COOKIE_MAX_AGE, samesite="Lax", secure=False)
    return resp

def require_gm():
    # einfacher Schutz: ?key=... oder Header X-GM-Key
    if not GM_KEY:
        return
    k = request.args.get("key") or request.headers.get("X-GM-Key")
    if k != GM_KEY:
        abort(403)



def within_one_edit(a: str, b: str) -> bool:
    """True, wenn a und b Edit-Distanz <= 1 haben (Insert/Delete/Replace eines Zeichens)."""
    if a == b:
        return True

    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False

    # gleiche Länge -> max 1 Replacement
    if la == lb:
        diffs = 0
        for ca, cb in zip(a, b):
            if ca != cb:
                diffs += 1
                if diffs > 1:
                    return False
        return True

    # Länge unterscheidet sich um 1 -> max 1 Insert/Delete
    # s = kürzer, t = länger
    if la < lb:
        s, t = a, b
    else:
        s, t = b, a

    i = j = 0
    used_edit = False
    while i < len(s) and j < len(t):
        if s[i] == t[j]:
            i += 1
            j += 1
        else:
            if used_edit:
                return False
            used_edit = True
            j += 1  # überspringe ein Zeichen im längeren String
    return True

def normalize_for_compare(s: str) -> str:
    s = (s or "").lower()

    # ä → ae etc. (optional, aber sinnvoll für DE)
    s = (
        s.replace("ä", "ae")
         .replace("ö", "oe")
         .replace("ü", "ue")
         .replace("ß", "ss")
    )

    # Zahlwörter ersetzen (Wortgrenzen beachten)
    for word, digit in NUMBER_WORDS.items():
        s = re.sub(rf"\b{word}\b", digit, s)

    # alles außer buchstaben & zahlen entfernen
    s = re.sub(r"[^a-z0-9]", "", s)

    return s

def answer_matches(user_answer: str, correct_answers, *, fuzzy: bool = True) -> bool:
    """
    correct_answers: str oder list[str]
    Vergleich findet auf normalize_for_compare() statt.
    """
    ua = normalize_for_compare(user_answer)

    if isinstance(correct_answers, list):
        ca_list = [normalize_for_compare(x) for x in correct_answers]
    else:
        ca_list = [normalize_for_compare(correct_answers)]

    # 1) exakter Match
    if ua in ca_list:
        return True

    # 2) fuzzy match (max 1 Tippfehler)
    if not fuzzy:
        return False

    # Sicherheitsbremse: bei sehr kurzen Strings keinen fuzzy-match
    # (sonst wäre z.B. "6" ~ "7" schon 1 Replacement)
    if len(ua) < 4:
        return False

    for ca in ca_list:
        # auch hier: kurze "richtige" Antworten besser nicht fuzzy machen
        if len(ca) < 4:
            continue
        if within_one_edit(ua, ca):
            return True

    return False

def get_progress():
    raw = request.cookies.get(PROGRESS_COOKIE, "0")
    try:
        p = int(raw)
    except ValueError:
        p = 0
    return max(0, p)

def set_progress_cookie(resp, progress: int):
    resp.set_cookie(PROGRESS_COOKIE, str(progress), max_age=COOKIE_MAX_AGE, samesite="Lax", secure=False)
    return resp

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/api/current")
def api_current():
    progress = get_progress()
    pid, pname = get_player_id_and_name()
    touch_player(pid, pname, progress)
    team = get_team(pid)
    players[pid]["team"] = team    

    route_titles = load_route(team)

    touch_player(pid, progress)
    players[pid]["team"] = team

    if progress >= len(route_titles):
        payload = {
            "done": True,
            "total": len(route_titles),
            "progress": progress,
            "team": team
        }
        resp = make_response(jsonify(payload))
        resp = set_team_cookie(resp, team)
        resp = set_player_cookies(resp, pid, pname)
        return resp

    title = route_titles[progress]
    q = BANK_BY_TITLE.get(title)
    if not q:
        return jsonify({"ok": False, "error": f"Route references unknown title: {title}", "team": team}), 500

    payload = {k: q.get(k) for k in ["title","prompt","hint","media","reaction_correct","reaction_wrong"]}
    payload.update({
        "done": False,
        "total": len(route_titles),
        "progress": progress,
        "team": team
    })

    resp = make_response(jsonify(payload))
    resp = set_team_cookie(resp, team)
    resp = set_player_cookies(resp, pid, pname)
    return resp
        
@app.post("/api/submit")
def api_submit():
    progress = get_progress()
    pid, pname = get_player_id_and_name()
    touch_player(pid, pname, progress)
    team = get_team(pid)
    players[pid]["team"] = team

    route_titles = load_route(team)

    touch_player(pid, progress)
    players[pid]["team"] = team

    # fertig?
    if progress >= len(route_titles):
        resp = make_response(jsonify({
            "ok": True,
            "already_done": True,
            "correct": True,
            "reaction": "Du bist schon fertig 🎉",
            "team": team
        }))
        resp = set_team_cookie(resp, team)
        resp = set_player_cookies(resp, pid, pname)
        return resp

    data = request.get_json(silent=True) or {}
    user_answer_raw = (data.get("answer", "") or "").strip()

    title = route_titles[progress]
    q = BANK_BY_TITLE.get(title)
    if not q:
        return jsonify({
            "ok": False,
            "error": f"Route references unknown title: {title}",
            "team": team
        }), 500

    raw_correct = q.get("answer", "")
    is_correct = answer_matches(user_answer_raw, raw_correct, fuzzy=True)

    # ✅ Attempt loggen (für GM)
    attempts.append({
        "ts": now_iso(),
        "player_id": pid,
        "player_name": pname,
        "team": team,
        "q_index": progress,
        "title": q.get("title", f"Q{progress+1}"),
        "answer": user_answer_raw,
        "correct": bool(is_correct),
    })

    if is_correct:
        reaction = q.get("reaction_correct") or "Richtig ✅"
        progress += 1

        # ✅ progress im tracking aktualisieren
        touch_player(pid, progress)
        players[pid]["team"] = team

        resp = make_response(jsonify({
            "ok": True,
            "correct": True,
            "progress": progress,
            "reaction": reaction,
            "team": team
        }))
        resp = set_progress_cookie(resp, progress)
        resp = set_team_cookie(resp, team)
        resp = set_player_cookies(resp, pid, pname)
        return resp

    # falsch
    reaction = q.get("reaction_wrong") or "Leider falsch."
    resp = make_response(jsonify({
        "ok": True,
        "correct": False,
        "reaction": reaction,
        "team": team
    }))
    resp = set_team_cookie(resp, team)
    resp = set_player_cookies(resp, pid, pname)
    return resp

@app.get("/api/gm/status")
def gm_status():
    require_gm()

    # Spielerliste sortiert nach last_seen (neueste zuerst)
    p = sorted(
        [{"player_id": pid, **info} for pid, info in players.items()],
        key=lambda x: x.get("last_seen", ""),
        reverse=True,
    )
    # Fortschritt in "aktuellen Titel" übersetzen (pro Team-Route!)
    for rec in p:
        idx = int(rec.get("progress", 0))
        team = rec.get("team") or "team1"

        try:
            route_titles = load_route(team)
        except Exception:
            route_titles = []

        if idx >= len(route_titles):
            rec["current"] = "DONE"
        else:
            rec["current"] = route_titles[idx]

    # letzte 200 Attempts zurückgeben
    last_attempts = attempts[-200:]

    return jsonify({
        "players": p,
        "attempts": last_attempts,
        "total_attempts": len(attempts),
        "server_time": now_iso(),
    })

@app.get("/api/reset_all")
def reset_all():
    require_gm()

    resp = make_response(jsonify({"ok": True}))

    # alle relevanten Cookies löschen
    for name in ["player_id", "team", "progress"]:
        resp.set_cookie(name, "", max_age=0)

    # optional: auch Server-State leeren
    players.clear()
    attempts.clear()

    return resp

@app.get("/gm")
def gm_page():
    require_gm()
    return """
<!doctype html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Game Master</title>
<style>
body{font-family:system-ui,Segoe UI,Arial;margin:16px;max-width:1100px}
h1{margin:0 0 10px}
small{color:#666}
.grid{display:grid;gap:14px}
.card{border:1px solid #ddd;border-radius:12px;padding:12px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:baseline}
code{background:#f3f3f3;padding:2px 6px;border-radius:6px}
.good{color:green} .bad{color:#b00020}
table{border-collapse:collapse;width:100%;margin-top:8px}
td,th{border:1px solid #eee;padding:6px;font-size:13px;vertical-align:top}
th{background:#fafafa;text-align:left}
.muted{color:#666}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;background:#f3f3f3}

/* Team pills */
.team-team1{background:#e8f0ff}
.team-team2{background:#e8fff1}
.team-team3{background:#fff6e8}
.team-team4{background:#ffe8f0}
.team-unknown{background:#f3f3f3}
</style></head><body>
<h1>Game Master</h1>
<small>Auto-Refresh alle 2s</small>
<div id="root">Lade…</div>

<script>
const root = document.getElementById('root');

function esc(s){
  return (s ?? "").toString()
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;");
}

function teamClass(team){
  const t = (team || "").toString();
  if (t === "team1" || t === "team2" || t === "team3" || t === "team4") return "team-" + t;
  return "team-unknown";
}

async function tick(){
  const res = await fetch('/api/gm/status' + location.search);
  const data = await res.json();

  const players = data.players || [];
  const attempts = data.attempts || [];

  // Attempts nach Player gruppieren (neueste zuerst)
  const byPlayer = {};
  for (const a of attempts.slice().reverse()) {
    const pid = a.player_id || "???";
    if (!byPlayer[pid]) byPlayer[pid] = [];
    byPlayer[pid].push(a);
  }

  let html = '';
  html += `<div class="row">
    <span class="pill">Spieler: ${players.length}</span>
    <span class="pill">Attempts: ${data.total_attempts || 0}</span>
    <span class="pill">Server: ${esc(data.server_time || "")}</span>
  </div>`;

  html += `<div class="grid">`;

  // players ist bereits serverseitig nach last_seen sortiert (wenn du gm_status so hast)
  for (const p of players) {
    const pid = p.player_id;
    const logs = byPlayer[pid] || [];
    const team = p.team || "?";
    const tClass = teamClass(team);

    html += `<div class="card">`;
    html += `<div class="row">
      <strong>${esc(pid)}</strong>
      <span class="muted">(${esc(p.user_agent || "")})</span>
    </div>`;

    html += `<div class="row">
      <span class="pill ${tClass}">Team: ${esc(team)}</span>
      <span class="pill">Progress: ${p.progress}</span>
      <span class="pill">Aktuell: ${esc(p.current || "")}</span>
      <span class="pill">Last seen: ${esc(p.last_seen || "")}</span>
    </div>`;

    html += `<table><tr><th>Zeit (UTC)</th><th>Frage</th><th>Antwort</th><th>Status</th></tr>`;

    // zeige pro Spieler max. 10 letzte Versuche
    const shown = logs.slice(0, 10);
    for (const a of shown) {
      const status = a.correct ? "✅" : "❌";
      const cls = a.correct ? "good" : "bad";
      html += `<tr>
        <td>${esc(a.ts || "")}</td>
        <td>#${(a.q_index+1)} ${esc(a.title || "")}</td>
        <td>${esc(a.answer || "")}</td>
        <td class="${cls}">${status}</td>
      </tr>`;
    }
    if (logs.length > 10) {
      html += `<tr><td colspan="4" class="muted">… ${logs.length - 10} weitere Versuche</td></tr>`;
    }

    html += `</table>`;
    html += `</div>`;
  }

  html += `</div>`;
  root.innerHTML = html;
}

tick();
setInterval(tick, 2000);
</script>
</body></html>
"""

@app.post("/api/reset")
def api_reset():
    resp = make_response(jsonify({"ok": True}))
    return set_progress_cookie(resp, 0)

if __name__ == "__main__":
    # Lokal: python app.py
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 80)), debug=False)
