"""Look and feel: CSS and small HTML helpers."""
import html

VERDICT_COLORS = {
    "LIKELY FAKE": "#ef4444",
    "LIKELY REAL": "#10b981",
    "UNVERIFIED": "#8b5cf6",
    "INSUFFICIENT INFORMATION": "#64748b",
    "TEST": "#38bdf8",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&display=swap');
:root { --gold:#f2b84b; --gold2:#e0a22a; --ink:#e9eefb; --mut:#8a97b8; --line:rgba(120,140,200,.16);
        --card:linear-gradient(160deg,rgba(18,28,58,.92),rgba(11,18,40,.92)); }
html, body, [class*="css"], .stApp { font-family:'Inter','Segoe UI',system-ui,sans-serif; }
.stApp { background: radial-gradient(1100px 520px at 12% -10%, rgba(80,110,255,.13), transparent 60%),
         radial-gradient(900px 500px at 100% 0%, rgba(242,184,75,.07), transparent 60%), #070c1b; }
header[data-testid="stHeader"] { background:transparent; }
.block-container { padding-top:2.4rem; max-width:1320px; }
h1,h2,h3 { color:var(--ink); letter-spacing:-.02em; font-weight:700; }
a { color:var(--gold); }

/* sidebar */
[data-testid="stSidebar"] { background:linear-gradient(180deg,#080e20,#0a1128); border-right:1px solid var(--line); }
.ts-logo { display:flex; align-items:center; gap:12px; margin:4px 0 6px; }
.ts-logo .mk { width:42px; height:42px; border-radius:13px; display:flex; align-items:center; justify-content:center;
        background:linear-gradient(135deg,#3b4bd8,#7c3aed); box-shadow:0 10px 24px -10px #6366f1; }
.ts-logo .mk svg { width:22px; height:22px; stroke:#fff; fill:none; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
.ts-logo .nm { font-weight:800; font-size:1.2rem; color:#fff; letter-spacing:-.02em; line-height:1.1; }
.ts-logo .nm span { color:var(--gold); }
.ts-logo .tg { font-size:.62rem; letter-spacing:.2em; color:var(--mut); font-weight:600; margin-top:2px; }
.ts-brand { font-size:1.4rem; font-weight:800; color:#fff; margin:0; } .ts-brand span { color:var(--gold); }
.ts-tag { color:var(--mut); font-size:.78rem; }
[data-testid="stSidebar"] [role="radiogroup"] { gap:3px; padding-top:6px; }
[data-testid="stSidebar"] [role="radiogroup"] label { position:relative; padding:9px 14px; border-radius:12px; width:100%;
        border:1px solid transparent; transition:all .16s ease; }
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background:rgba(120,140,200,.10); }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background:rgba(242,184,75,.10);
        border-color:rgba(242,184,75,.38); box-shadow:inset 3px 0 0 var(--gold); }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p { color:#fff; }
[data-testid="stSidebar"] [role="radiogroup"] label p { font-weight:600; font-size:.92rem; color:#b4c0df; }
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child:not(:has(p)) { display:none !important; }
[data-testid="stSidebar"] [role="radiogroup"] label [data-baseweb="radio"] > div:first-child { display:none; }
[data-testid="stSidebar"] [role="radiogroup"] label:nth-child(1),[data-testid="stSidebar"] [role="radiogroup"] label:nth-child(3),
[data-testid="stSidebar"] [role="radiogroup"] label:nth-child(5),[data-testid="stSidebar"] [role="radiogroup"] label:nth-child(7),
[data-testid="stSidebar"] [role="radiogroup"] label:nth-child(9) { margin-top:30px; }
[data-testid="stSidebar"] [role="radiogroup"] label:nth-child(-n+9)::before { position:absolute; top:-22px; left:6px;
        font-size:.64rem; letter-spacing:.2em; font-weight:700; color:#5d6b8f; }
[data-testid="stSidebar"] [role="radiogroup"] label:nth-child(1)::before { content:"OVERVIEW"; }
[data-testid="stSidebar"] [role="radiogroup"] label:nth-child(3)::before { content:"VERIFY"; }
[data-testid="stSidebar"] [role="radiogroup"] label:nth-child(5)::before { content:"DISPLAY"; }
[data-testid="stSidebar"] [role="radiogroup"] label:nth-child(7)::before { content:"ACCOUNT"; }
[data-testid="stSidebar"] [role="radiogroup"] label:nth-child(9)::before { content:"ADMINISTRATION"; }
.ts-dl { margin-top:14px; padding:14px 16px; border-radius:16px; background:linear-gradient(160deg,rgba(60,80,200,.22),rgba(20,30,70,.5));
        border:1px solid rgba(120,140,255,.25); }
.ts-dl b { color:#fff; font-size:.9rem; } .ts-dl div { color:var(--mut); font-size:.76rem; margin:3px 0 6px; }
.ts-dl span { color:var(--gold); font-size:.78rem; font-weight:700; }

/* page header */
.ts-ph { margin:0 0 22px; }
.ts-ph .k { color:var(--gold); font-size:.72rem; font-weight:700; letter-spacing:.24em; text-transform:uppercase; }
.ts-ph .t { font-size:2.15rem; font-weight:800; color:#fff; letter-spacing:-.035em; line-height:1.15; margin:4px 0 6px; }
.ts-ph .s { color:#9fb0d6; font-size:.98rem; max-width:760px; }
.ts-chips { margin-top:12px; display:flex; flex-wrap:wrap; gap:8px; }
.ts-chip { padding:4px 12px; border-radius:999px; font-size:.72rem; font-weight:600; color:#cdd8f4;
        background:rgba(120,140,200,.10); border:1px solid var(--line); }
.ts-hero { border-radius:22px; padding:34px; margin-bottom:18px; background:linear-gradient(135deg,rgba(80,110,255,.18),rgba(124,58,237,.16));
        border:1px solid rgba(130,150,255,.28); }
.ts-hero .k { color:var(--gold); font-size:.72rem; font-weight:700; letter-spacing:.24em; text-transform:uppercase; }
.ts-hero .t { font-size:2.4rem; font-weight:800; color:#fff; letter-spacing:-.035em; margin:6px 0; }
.ts-hero .s { color:#b8c6ea; max-width:640px; }

/* cards, stat cards */
.ts-card { background:var(--card); border:1px solid var(--line); border-radius:20px; padding:18px 20px; margin-bottom:14px; }
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"] .ts-ct) { background:var(--card);
        border:1px solid var(--line) !important; border-radius:22px; padding:6px 10px; box-shadow:0 22px 50px -34px #000; }
.ts-ct .a { font-size:1rem; font-weight:700; color:#fff; } .ts-ct .b { font-size:.76rem; color:var(--mut); margin-bottom:6px; }
.ts-metric { position:relative; background:var(--card); border:1px solid var(--line); border-radius:20px; padding:16px 18px;
        min-height:104px; transition:all .2s ease; box-shadow:0 18px 40px -30px #000; }
.ts-metric:hover { transform:translateY(-3px); border-color:rgba(242,184,75,.45); box-shadow:0 18px 40px -22px rgba(242,184,75,.35); }
.ts-metric .l { font-size:.66rem; color:var(--mut); text-transform:uppercase; letter-spacing:.16em; font-weight:700; max-width:70%; }
.ts-metric .v { font-size:2.15rem; font-weight:800; color:#fff; letter-spacing:-.03em; margin-top:8px; line-height:1; }
.ts-metric .ic { position:absolute; right:14px; top:14px; width:34px; height:34px; border-radius:11px; display:flex;
        align-items:center; justify-content:center; background:rgba(120,140,200,.12); border:1px solid var(--line); }
.ts-metric .ic svg, .ts-ico { width:17px; height:17px; fill:none; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
.ts-badge { display:inline-block; padding:4px 12px; border-radius:999px; font-weight:700; font-size:.72rem; letter-spacing:.08em; border:1px solid; }
.ts-dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:7px; }
.ts-muted { color:var(--mut); font-size:.85rem; }
.ts-note { border-left:3px solid var(--gold); padding:9px 14px; background:rgba(14,24,50,.75); border-radius:0 12px 12px 0; color:#bccaea; font-size:.88rem; }
.ts-section { display:flex; align-items:center; gap:10px; margin:28px 0 12px; }
.ts-section .bar { width:4px; height:18px; border-radius:4px; background:linear-gradient(180deg,var(--gold),#f59e0b); }
.ts-section .h { font-size:1.1rem; font-weight:700; color:#fff; letter-spacing:-.02em; }

/* verdict */
.ts-verdict { border-radius:22px; padding:24px 26px; margin:6px 0 14px; border:1px solid; }
.ts-verdict .vt { font-size:2rem; font-weight:800; letter-spacing:-.03em; margin:10px 0 6px; }
.ts-verdict .vr { color:#d7e1f7; } .ts-verdict .vm { color:var(--mut); font-size:.78rem; font-family:'JetBrains Mono',monospace; margin-top:6px; }

/* tables / legend */
table.ts-tbl { width:100%; border-collapse:collapse; font-size:.86rem; }
.ts-tbl th { text-align:left; color:var(--mut); font-size:.64rem; letter-spacing:.16em; font-weight:700; padding:8px 6px; border-bottom:1px solid var(--line); }
.ts-tbl td { padding:12px 6px; border-bottom:1px solid rgba(120,140,200,.08); color:#dbe4fb; }
.ts-tbl tr:last-child td { border-bottom:0; } .ts-tbl td.hd { font-weight:600; color:#fff; max-width:360px; }
.ts-leg { display:flex; justify-content:space-between; font-size:.82rem; padding:5px 0; color:#c8d3ef; }
.ts-leg b { color:#fff; }

/* workflow */
.ts-flow { display:grid; grid-template-columns:repeat(5,1fr); gap:12px; }
.ts-step { background:var(--card); border:1px solid var(--line); border-radius:18px; padding:14px; transition:all .2s ease; }
.ts-step:hover { transform:translateY(-3px); border-color:rgba(242,184,75,.5); }
.ts-step .n { width:28px; height:28px; border-radius:50%; display:flex; align-items:center; justify-content:center;
        font-weight:800; font-size:.8rem; color:#1a1204; background:linear-gradient(135deg,#f7c85f,#e0a22a); }
.ts-step .a { font-weight:700; font-size:.92rem; color:#fff; margin:9px 0 3px; } .ts-step .b { color:var(--mut); font-size:.76rem; line-height:1.4; }
.ts-dev { display:flex; align-items:center; justify-content:space-between; gap:14px; background:var(--card);
        border:1px solid var(--line); border-radius:16px; padding:14px 18px; margin-bottom:10px; }
.ts-dev .nm { font-weight:700; color:#fff; }
.ts-pin { font-family:'JetBrains Mono',monospace; font-size:.76rem; color:var(--gold); background:rgba(242,184,75,.1);
        border:1px solid rgba(242,184,75,.3); padding:2px 8px; border-radius:8px; }
@media (max-width:1000px) { .ts-flow { grid-template-columns:repeat(2,1fr); } }

/* inputs, buttons, tabs */
div.stButton > button, div.stDownloadButton > button { border-radius:12px; border:1px solid rgba(120,140,200,.3);
        background:rgba(18,28,58,.8); font-weight:600; transition:all .16s ease; }
div.stButton > button:hover { border-color:var(--gold); transform:translateY(-1px); }
div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] {
        background:linear-gradient(180deg,#f7c85f,#e0a22a); color:#1a1204; border:0; font-weight:800;
        box-shadow:0 10px 24px -12px rgba(242,184,75,.9); }
div.stButton > button[kind="primary"]:hover { filter:brightness(1.07); box-shadow:0 14px 30px -12px rgba(242,184,75,1); }
textarea, input[type="text"], input[type="password"], div[data-baseweb="select"] > div {
        background:rgba(8,13,30,.8) !important; border-radius:12px !important; border-color:var(--line) !important; }
textarea:focus, input:focus { border-color:var(--gold) !important; box-shadow:0 0 0 3px rgba(242,184,75,.16) !important; }
[data-baseweb="tab-list"] { gap:6px; border-bottom:1px solid var(--line); }
button[data-baseweb="tab"] { border-radius:10px 10px 0 0; padding:10px 18px; font-weight:600; }
[data-baseweb="tab-highlight"] { background:var(--gold) !important; height:3px !important; }
[data-testid="stExpander"] { background:var(--card); border:1px solid var(--line) !important; border-radius:16px; }
[data-testid="stFileUploaderDropzone"] { border:1.5px dashed rgba(242,184,75,.45); border-radius:16px; background:rgba(242,184,75,.04); }
[data-testid="stDataFrame"] { border-radius:14px; overflow:hidden; }
hr { border-color:var(--line) !important; }
::-webkit-scrollbar { width:8px; } ::-webkit-scrollbar-thumb { background:#223356; border-radius:8px; }
@media (max-width:640px) { .ts-metric .v { font-size:1.6rem; } .ts-ph .t { font-size:1.6rem; } }
</style>
"""


ICONS = {
    "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "shield-check": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "shield-x": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9.5 9.5 5 5m0-5-5 5"/>',
    "alert": '<path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3z"/><path d="M12 9v4M12 17h.01"/>',
    "help": '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
    "wifi": '<path d="M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M12 20h.01"/>',
    "send": '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
}
TONES = {"gold": "#f2b84b", "green": "#10b981", "red": "#ef4444", "purple": "#8b5cf6", "amber": "#f59e0b",
         "grey": "#94a3b8", "blue": "#60a5fa"}


def icon(name, tone="gold"):
    return (f'<svg class="ts-ico" viewBox="0 0 24 24" style="stroke:{TONES.get(tone, tone)}">'
            f'{ICONS.get(name, "")}</svg>')


def esc(s):
    return html.escape(str(s if s is not None else ""))


def badge(verdict):
    col = VERDICT_COLORS.get(verdict, "#64748b")
    return (f'<span class="ts-badge" style="color:{col};border-color:{col};'
            f'background:{col}1f">{esc(verdict)}</span>')


def metric(label, value, ic=None, tone="gold"):
    i = f'<div class="ic">{icon(ic, tone)}</div>' if ic else ""
    return f'<div class="ts-metric"><div class="l">{esc(label)}</div>{i}<div class="v">{esc(value)}</div></div>'


def logo():
    return ('<div class="ts-logo"><div class="mk"><svg viewBox="0 0 24 24">' + ICONS["shield"] + '</svg></div>'
            '<div><div class="nm">TruthSync <span>AI</span></div><div class="tg">VERIFY BEFORE YOU BELIEVE</div></div></div>')


def display_link():
    return ('<div class="ts-dl"><b>Display link</b><div>Verdicts reach your ESP32 OLED automatically.</div>'
            '<span>Manage devices in Device Management</span></div>')


def card_title(title, sub=""):
    return f'<div class="ts-ct"><div class="a">{esc(title)}</div><div class="b">{esc(sub)}</div></div>'


def recent_table(rows):
    body = "".join(
        f'<tr><td class="hd">{esc((r["content"] or "")[:70])}</td><td>{esc(r["input_type"])}</td>'
        f'<td>{badge(r["verdict"])}</td><td class="ts-muted">{esc(str(r["created_at"])[:10])}</td></tr>' for r in rows)
    return ('<table class="ts-tbl"><tr><th>HEADLINE</th><th>TYPE</th><th>VERDICT</th><th>DATE</th></tr>'
            + body + '</table>')


def legend(counts):
    total = sum(counts.values()) or 1
    return "".join(
        f'<div class="ts-leg"><span><span class="ts-dot" style="background:{VERDICT_COLORS.get(k, "#64748b")}"></span>'
        f'{esc(k.title())}</span><b>{round(100 * v / total)}%</b></div>' for k, v in counts.items())


def status_dot(online):
    col = "#22c55e" if online else "#64748b"
    return f'<span class="ts-dot" style="background:{col}"></span>' + ("Online" if online else "Offline")


def md_link(title, url):
    t = (title or url or "source").replace("[", "(").replace("]", ")").replace("\n", " ")[:110]
    safe = (url or "").replace(" ", "%20").replace(")", "%29")
    if not safe.lower().startswith(("http://", "https://")):
        return t
    return f"[{t}]({safe})"


def csv_safe(v):
    """Prevents spreadsheet formula injection in CSV exports."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def hero(kicker, title, sub, chips=()):
    ch = "".join(f'<span class="ts-chip">{esc(c)}</span>' for c in chips)
    return (f'<div class="ts-ph"><div class="k">{esc(kicker)}</div><div class="t">{esc(title)}</div>'
            f'<div class="s">{esc(sub)}</div><div class="ts-chips">{ch}</div></div>')


def landing(kicker, title, sub, chips=()):
    ch = "".join(f'<span class="ts-chip">{esc(c)}</span>' for c in chips)
    return (f'<div class="ts-hero"><div class="k">{esc(kicker)}</div><div class="t">{esc(title)}</div>'
            f'<div class="s">{esc(sub)}</div><div class="ts-chips">{ch}</div></div>')


def section(title):
    return f'<div class="ts-section"><div class="bar"></div><div class="h">{esc(title)}</div></div>'


def verdict_card(verdict, reason, meta):
    col = VERDICT_COLORS.get(verdict, "#64748b")
    return (f'<div class="ts-verdict" style="border-color:{col}66;'
            f'background:linear-gradient(135deg,{col}26,rgba(8,14,32,.6));box-shadow:0 20px 50px -30px {col}">'
            f'{badge(verdict)}<div class="vt" style="color:{col}">{esc(verdict)}</div>'
            f'<div class="vr">{esc(reason)}</div><div class="vm">{esc(meta)}</div></div>')


FLOW = [
    ("Authenticate", "Sign up, login, forgot password, profile"),
    ("Submit news", "Text, image, URL or social post"),
    ("AI analysis", "Extract text, find claims, check evidence"),
    ("Store result", "Saved to your private history and reports"),
    ("Pick devices", "One, several or all ESP32 displays"),
    ("API delivery", "Secure per-device message with API key"),
    ("ESP32 fetches", "Wi-Fi polling every 2 seconds"),
    ("OLED shows it", "Verdict and report ID on the SSD1306"),
    ("Acknowledge", "Device confirms it really displayed it"),
    ("Monitor", "Online status, delivery logs and reports"),
]


def pipeline():
    cells = "".join(f'<div class="ts-step"><div class="n">{i}</div><div class="a">{esc(a)}</div>'
                    f'<div class="b">{esc(b)}</div></div>' for i, (a, b) in enumerate(FLOW, 1))
    return f'<div class="ts-flow">{cells}</div>'
