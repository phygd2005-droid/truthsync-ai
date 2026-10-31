"""TruthSync AI - Streamlit app.   Run:  streamlit run app.py"""
import io
import os
import re
import secrets
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st

import env_loader  # noqa: F401  (must come first)
import devices
import engine
import mailer
import security
import store
from db import TS_FMT, audit, db, init_db, local_ts, notify, now, seconds_since
from ui import (CSS, VERDICT_COLORS, badge, card_title, csv_safe, display_link, esc, hero, landing, legend,
                logo, md_link, metric, pipeline, recent_table, section, status_dot, verdict_card)

st.set_page_config(page_title="TruthSync AI", page_icon="🛡️", layout="wide")

# Streamlit Cloud keeps secrets in st.secrets; copy them into the environment so that every
# module (engine, mailer...) can read them the same way as local .env values.
for _k in ("OCR_SPACE_KEY", "GOOGLE_FACTCHECK_KEY", "SMTP_HOST", "SMTP_PORT", "SMTP_USER",
           "SMTP_PASS", "SMTP_FROM", "ADMIN_EMAIL", "DEV_MODE", "API_BASE_URL"):
    try:
        _v = st.secrets[_k]
    except Exception:
        _v = None
    if _v and not os.environ.get(_k):
        os.environ[_k] = str(_v)

init_db()
st.markdown(CSS, unsafe_allow_html=True)

PAGES = [
    ("overview", "Overview"), ("analytics", "Analytics"), ("verify", "Verify Content"),
    ("history", "Verification History"), ("devices", "Device Management"), ("notifications", "Notifications"),
    ("profile", "Profile & Settings"), ("help", "Help & Documentation"), ("admin", "Admin Dashboard"),
]
PAGE_ICON = {"overview": "dashboard", "analytics": "bar_chart", "verify": "fact_check", "history": "history",
             "devices": "developer_board", "notifications": "notifications", "profile": "person",
             "help": "help", "admin": "admin_panel_settings"}
BASIS_LABEL = {
    "evidence": "Evidence-based assessment (web / fact-check sources compared)",
    "curated": "Curated fact entry (written by the project owner, not live data)",
    "model": "Model prediction only (writing style, NOT a fact check)",
    "none": "No assessment possible",
}


# ================================================================== helpers
def current_user():
    uid = st.session_state.get("uid")
    if not uid:
        return None
    with db() as c:
        row = c.execute("SELECT * FROM users WHERE id=? AND is_active=1", (uid,)).fetchone()
    if row is None:
        st.session_state.pop("uid", None)
        return None
    return dict(row)


def plotly_dark(fig):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=40, b=10))
    return fig


def metrics_row(items):
    cols = st.columns(len(items))
    for col, it in zip(cols, items):
        col.markdown(metric(*it), unsafe_allow_html=True)


def auth_page():
    st.markdown(landing("TruthSync AI", "Verify Before You Believe.", "AI-powered news verification with evidence analysis and live ESP32 OLED display.", ["Text","Image","URL","Evidence-based","ESP32 + OLED"]), unsafe_allow_html=True)
    tab_in, tab_reg, tab_forgot = st.tabs(["Sign in", "Create account", "Forgot password"])

    with tab_in:
        with st.form("login"):
            email = st.text_input("Email")
            pw = st.text_input("Password", type="password")
            go = st.form_submit_button("Sign in", type="primary")
        if go:
            if time.time() < st.session_state.get("lock_until", 0):
                st.error("Too many failed attempts. Please wait a minute and try again.")
            else:
                with db() as c:
                    u = c.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
                    ok = bool(u) and bool(u["is_active"]) and security.verify_password(pw, u["pw_hash"])
                    audit(c, u["id"] if u else None, "login_ok" if ok else "login_failed",
                          email.strip().lower()[:80])
                if ok:                                  # rerun AFTER the database block commits
                    st.session_state["uid"] = u["id"]
                    st.session_state["fails"] = 0
                    st.rerun()
                st.session_state["fails"] = st.session_state.get("fails", 0) + 1
                if st.session_state["fails"] >= 5:
                    st.session_state["lock_until"] = time.time() + 60
                    st.session_state["fails"] = 0
                st.error("Incorrect email or password.")

    with tab_reg:
        with st.form("register"):
            name = st.text_input("Full name")
            email = st.text_input("Email", key="reg_email")
            pw = st.text_input("Password (8+ characters, upper/lower case and a number)", type="password", key="reg_pw")
            pw2 = st.text_input("Confirm password", type="password")
            go = st.form_submit_button("Create account", type="primary")
        if go:
            email = email.strip().lower()
            problem = (security.password_problem(pw) if pw else "Enter a password.")
            if not name.strip():
                st.error("Please enter your name.")
            elif not security.valid_email(email):
                st.error("Please enter a valid email address.")
            elif problem:
                st.error(problem)
            elif pw != pw2:
                st.error("The two passwords do not match.")
            else:
                # Only the email set in ADMIN_EMAIL becomes admin. Nobody can pick a role.
                role = "admin" if email == os.environ.get("ADMIN_EMAIL", "").strip().lower() else "user"
                try:
                    with db() as c:
                        c.execute("INSERT INTO users(email,name,pw_hash,role,created_at) VALUES (?,?,?,?,?)",
                                  (email, name.strip()[:60], security.hash_password(pw), role, now()))
                        audit(c, None, "register", email)
                    st.success("Account created. You can sign in now.")
                except Exception:
                    st.error("An account with this email already exists.")

    with tab_forgot:
        dev_mode = os.environ.get("DEV_MODE") == "1"
        email = st.text_input("Account email", key="fp_email")
        if st.button("Send reset code"):
            token, user = None, None
            with db() as c:
                user = c.execute("SELECT * FROM users WHERE email=? AND is_active=1",
                                 (email.strip().lower(),)).fetchone()
                if user:
                    token = secrets.token_urlsafe(12)
                    exp = (datetime.now(timezone.utc) + timedelta(minutes=30)).strftime(TS_FMT)
                    c.execute("UPDATE users SET reset_hash=?, reset_expires=? WHERE id=?",
                              (security.hash_token(token), exp, user["id"]))
                    audit(c, user["id"], "password_reset_requested", "")
            if mailer.smtp_configured():
                if user:
                    mailer.send_email(user["email"], "TruthSync AI password reset",
                                      f"Your reset code (valid 30 minutes): {token}")
                st.success("If that account exists, a reset code has been emailed.")
            elif dev_mode and token:
                st.warning("DEVELOPMENT MODE ONLY: email is not configured, so the code is shown "
                           "here. Never enable DEV_MODE on a public server.")
                st.code(token)
            else:
                st.error("Email sending is not configured on this server, so password reset "
                         "is unavailable. Ask the administrator.")
        st.markdown("**Have a code?**")
        with st.form("reset"):
            r_email = st.text_input("Email", key="rs_email")
            r_code = st.text_input("Reset code")
            r_pw = st.text_input("New password", type="password", key="rs_pw")
            go = st.form_submit_button("Set new password")
        if go:
            problem = security.password_problem(r_pw)
            with db() as c:
                u = c.execute("SELECT * FROM users WHERE email=?", (r_email.strip().lower(),)).fetchone()
                valid = (u and u["reset_hash"] and u["reset_expires"] and u["reset_expires"] >= now()
                         and security.hash_token(r_code.strip()) == u["reset_hash"])
                if problem:
                    st.error(problem)
                elif not valid:
                    st.error("That code is wrong or has expired.")
                else:
                    c.execute("UPDATE users SET pw_hash=?, reset_hash=NULL, reset_expires=NULL WHERE id=?",
                              (security.hash_password(r_pw), u["id"]))
                    audit(c, u["id"], "password_reset_done", "")
                    st.success("Password updated. You can sign in now.")


# ================================================================== reports
def render_report(r):
    st.markdown(verdict_card(r["verdict"], r["reason"], f'Report {r["report_id"]} · {r["input_type"]} · {local_ts(r["created_at"])}'),
                unsafe_allow_html=True)
    st.markdown(f"**Assessment type:** {BASIS_LABEL.get(r['basis'], '-')}")
    st.markdown(f"**Method:** {esc(r['method'])}")
    st.markdown("**Confidence:** not shown - the engine has no calibrated confidence score, and "
                "showing an invented percentage would be misleading.")
    if r.get("source_url"):
        st.markdown(f"**Source URL:** {md_link(r['source_url'], r['source_url'])}")
    if r.get("retrieved_at"):
        st.markdown(f"**Evidence retrieved:** {esc(local_ts(r['retrieved_at']))}")
    with st.expander("Claims identified", expanded=True):
        for cl in r["claims"] or ["-"]:
            st.markdown(f"- {esc(cl)}")
    ev = r["evidence"]
    for key, title in (("supporting", "Supporting evidence"), ("contradicting", "Contradicting evidence"),
                       ("related", "Related sources (neither confirm nor deny)")):
        items = ev.get(key, [])
        with st.expander(f"{title} ({len(items)})", expanded=bool(items) and key != "related"):
            if not items:
                st.caption("None found.")
            for e in items:
                st.markdown(f"- {md_link(e['title'], e['url'])} &nbsp; <span class='ts-muted'>"
                            f"{esc(e.get('stance', ''))}</span>", unsafe_allow_html=True)
    with st.expander("Limitations", expanded=True):
        for lim in r["limitations"]:
            st.markdown(f"- {esc(lim)}")
    with st.expander("Submitted content"):
        st.text(r["content"])


def send_panel(uid, vid):
    with db() as c:
        devs = c.execute("SELECT * FROM devices WHERE user_id=? AND revoked=0 "
                         "ORDER BY is_default DESC, name", (uid,)).fetchall()
    st.markdown("##### Send to ESP32 OLED display")
    if not devs:
        st.info("You have no devices yet. Register one under Device Management.")
        return
    mode = st.radio("Send to", ["Default device", "Selected devices", "All my devices"],
                    horizontal=True, key=f"mode{vid}")
    if mode == "Default device":
        pks = [devs[0]["id"]]
        st.caption(f"Default: {devs[0]['name']}")
    elif mode == "All my devices":
        pks = [d["id"] for d in devs]
    else:
        opts = {f"{d['name']} ({d['device_id']})": d["id"] for d in devs}
        pks = [opts[k] for k in st.multiselect("Devices", list(opts), key=f"sel{vid}")]
    if st.button("Send to display", key=f"send{vid}", disabled=not pks):
        with db() as c:
            ids = devices.queue_message(c, uid, vid, pks)
        st.success(f"Queued for {len(ids)} device(s). Status stays 'pending/sent' until the "
                   "ESP32 confirms it displayed the message.")


def show_result(uid, vid):
    with db() as c:
        r = store.get_report(c, uid, vid)
    if r:
        st.divider()
        render_report(r)
        n = st.session_state.get("auto_sent", 0)
        if n and n > 0:
            st.success(f"Sent automatically to your OLED display ({n} device(s)).")
        elif n == 0:
            st.caption("No OLED device registered yet. Add one under Device Management and "
                       "future results will appear on it automatically.")


def finish(uid, input_type, content, rep, source_url=None):
    with db() as c:
        vid = store.save_verification(c, uid, input_type, content, rep, source_url)
        # AUTO-SEND: every finished verification (text, image, URL, social post) goes to
        # all of this user's active OLED devices. No button needed.
        try:
            pks = [d["id"] for d in c.execute(
                "SELECT id FROM devices WHERE user_id=? AND revoked=0", (uid,)).fetchall()]
            st.session_state["auto_sent"] = len(devices.queue_message(c, uid, vid, pks)) if pks else 0
        except Exception:
            st.session_state["auto_sent"] = -1
    st.session_state["last_vid"] = vid


def run_text(uid, text, input_type="text", limits=None, source_url=None):
    use_web = st.session_state.get("use_web", True)
    with st.spinner("Checking the claim against online evidence..."):
        try:
            rep = engine.verify_content(text, input_type, use_web,
                                        os.environ.get("GOOGLE_FACTCHECK_KEY", ""),
                                        source_url=source_url, extra_limitations=limits)
        except Exception as e:
            with db() as c:
                audit(c, uid, "error", f"verify {type(e).__name__}")
            st.error("Something went wrong while verifying. Please try again.")
            return
    finish(uid, input_type, engine.normalize(text), rep, source_url)


def load_image(up):
    from PIL import Image
    data = up.getvalue()
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("The image is larger than 5 MB.")
    im = Image.open(io.BytesIO(data))
    im.verify()
    im = Image.open(io.BytesIO(data))
    if im.format not in ("JPEG", "PNG"):
        raise ValueError("Only JPG and PNG images are supported.")
    if im.width * im.height > 25_000_000:
        raise ValueError("The image has too many pixels (limit 25 megapixels).")
    return im.convert("RGB")


# ================================================================== pages
def page_overview(user):
    import plotly.graph_objects as go
    uid = user["id"]
    with db() as c:
        devices.sweep(c)
        by_v = {r["verdict"]: r["n"] for r in c.execute(
            "SELECT verdict, COUNT(*) n FROM verifications WHERE user_id=? GROUP BY verdict", (uid,))}
        devs = c.execute("SELECT * FROM devices WHERE user_id=? AND revoked=0", (uid,)).fetchall()
        dl = {r["status"]: r["n"] for r in c.execute(
            "SELECT dl.status, COUNT(*) n FROM deliveries dl JOIN devices d ON d.id=dl.device_pk "
            "WHERE d.user_id=? GROUP BY dl.status", (uid,))}
        recent = c.execute("SELECT id, report_id, created_at, input_type, verdict, content FROM "
                           "verifications WHERE user_id=? ORDER BY id DESC LIMIT 6", (uid,)).fetchall()
        trend = c.execute("SELECT substr(created_at,1,10) d, verdict, COUNT(*) n FROM verifications WHERE user_id=? "
                          "AND created_at >= ? GROUP BY d, verdict ORDER BY d",
                          (uid, (datetime.now(timezone.utc) - timedelta(days=14)).strftime(TS_FMT))).fetchall()
    online = sum(1 for d in devs if devices.is_online(d["last_seen"]))
    total = sum(by_v.values())
    st.markdown(hero("Command centre", f"Welcome back, {user['name'].split()[0]}",
                     "Live verification counts, evidence trends and the state of your ESP32 delivery pipeline.",
                     ["Evidence-based", "ESP32 + OLED", "Private history"]), unsafe_allow_html=True)
    metrics_row([("Total analyses", total, "activity", "gold"),
                 ("Likely real", by_v.get("LIKELY REAL", 0), "shield-check", "green"),
                 ("Likely fake", by_v.get("LIKELY FAKE", 0), "shield-x", "red"),
                 ("Unverified", by_v.get("UNVERIFIED", 0), "help", "purple"),
                 ("Insufficient info", by_v.get("INSUFFICIENT INFORMATION", 0), "alert", "amber"),
                 ("Devices online", f"{online}/{len(devs)}", "cpu", "blue")])
    st.write("")
    left, right = st.columns([5, 3])
    with left:
        with st.container(border=True):
            st.markdown(card_title("Verification trend", "Classifications over the last 14 days"), unsafe_allow_html=True)
            if trend:
                df = pd.DataFrame([dict(r) for r in trend])
                days = pd.date_range(end=datetime.now(timezone.utc).date(), periods=14).strftime("%Y-%m-%d")
                fig = go.Figure()
                for v, col in VERDICT_COLORS.items():
                    sub = df[df["verdict"] == v].set_index("d")["n"].reindex(days, fill_value=0)
                    if sub.sum():
                        fig.add_trace(go.Scatter(x=days, y=sub.values, name=v.title(), mode="lines",
                                                 line=dict(color=col, width=2.5, shape="spline"),
                                                 fill="tozeroy", fillcolor=col + "26"))
                fig.update_layout(height=300, legend=dict(orientation="h", y=1.12, x=0),
                                  xaxis=dict(showgrid=False), yaxis=dict(gridcolor="rgba(120,140,200,.12)", dtick=1))
                st.plotly_chart(plotly_dark(fig), config={"displayModeBar": False})
            else:
                st.caption("The chart appears after your first verification.")
    with right:
        with st.container(border=True):
            st.markdown(card_title("Classification distribution", "Share of all saved verdicts"), unsafe_allow_html=True)
            if total:
                fig = go.Figure(go.Pie(labels=list(by_v), values=list(by_v.values()), hole=.74, sort=False,
                                       marker=dict(colors=[VERDICT_COLORS.get(k, "#64748b") for k in by_v],
                                                   line=dict(color="#0b1229", width=3)), textinfo="none"))
                fig.update_layout(height=230, showlegend=False, annotations=[dict(
                    text=f"<b style='font-size:30px'>{total}</b><br><span style='font-size:11px;color:#8a97b8'>RESULTS</span>",
                    showarrow=False, font=dict(color="#fff"))])
                st.plotly_chart(plotly_dark(fig), config={"displayModeBar": False})
                st.markdown(legend(by_v), unsafe_allow_html=True)
            else:
                st.info("No verifications yet. Run your first one below.")
    st.write("")
    l2, r2 = st.columns([5, 3])
    with l2:
        with st.container(border=True):
            st.markdown(card_title("Recent verifications", "Your latest reports"), unsafe_allow_html=True)
            if recent:
                st.markdown(recent_table(recent), unsafe_allow_html=True)
            else:
                st.caption("Nothing here yet.")
    with r2:
        with st.container(border=True):
            st.markdown(card_title("Quick verification", "Paste a headline or claim. The full evidence report opens below."),
                        unsafe_allow_html=True)
            text = st.text_area("Claim", height=110, key="quick_text", label_visibility="collapsed",
                                placeholder="e.g. Government announces a nationwide power cut next Tuesday")
            if st.button("Verify", type="primary", key="quick_go"):
                if text.strip():
                    run_text(uid, text)
                else:
                    st.warning("Please paste some text first.")
    if st.session_state.get("last_vid"):
        show_result(uid, st.session_state["last_vid"])
    st.markdown(section("Device connection status"), unsafe_allow_html=True)
    if devs:
        for d in devs:
            st.markdown(f'<div class="ts-dev"><div><div class="nm">{esc(d["name"])}</div>'
                        f'<div class="ts-muted">last seen {esc(local_ts(d["last_seen"]) if d["last_seen"] else "never")}</div></div>'
                        f'<div><span class="ts-pin">SDA 26</span> <span class="ts-pin">SCL 27</span> &nbsp; '
                        f'{status_dot(devices.is_online(d["last_seen"]))}</div></div>', unsafe_allow_html=True)
    else:
        st.caption("No devices registered. Add your ESP32 in Device Management.")
    st.markdown(section("How TruthSync works"), unsafe_allow_html=True)
    st.markdown(pipeline(), unsafe_allow_html=True)


def page_verify(user):
    uid = user["id"]
    st.markdown(hero("Verify", "Verify Content", "Submit text, an image, a URL or a social post for evidence-based checking.", ["Text","Image / OCR","URL","Social link"]), unsafe_allow_html=True)
    st.checkbox("Search the web for evidence", value=True, key="use_web",
                help="Turn off to run only the curated facts and the writing-style model.")
    t_text, t_img, t_url, t_soc = st.tabs(["Text", "Image", "URL", "Social media"])

    with t_text:
        text = st.text_area("Paste a headline, article, claim or statement", height=180, key="v_text")
        if st.button("Verify text", type="primary", key="v_text_go"):
            if text.strip():
                run_text(uid, text)
            else:
                st.warning("Please paste some text first.")

    with t_img:
        up = st.file_uploader("Upload a JPG or PNG", type=["jpg", "jpeg", "png"], key="v_img")
        if up:
            try:
                im = load_image(up)
                st.image(im, width=420)
                if st.button("Verify image", type="primary", key="v_img_go"):
                    with st.spinner("Reading text from the image..."):
                        text, err = engine.ocr_image(im)
                    if not text.strip():
                        st.warning("No readable text was found in the image. "
                                   + (f"({err})" if err else ""))
                    else:
                        run_text(uid, text, "image", limits=[
                            "Only the text inside the image was checked. The image itself was NOT "
                            "analysed for editing or AI generation, so this does not prove the "
                            "image is authentic.", "OCR can misread text; check the extracted text."])
            except Exception as e:
                st.error(str(e) if isinstance(e, ValueError) else "That file is not a valid image.")

    with t_url:
        url = st.text_input("Public news article link (http/https)", key="v_url")
        if st.button("Verify link", type="primary", key="v_url_go"):
            try:
                with st.spinner("Downloading the article and checking it..."):
                    rep = engine.verify_url(url.strip(), st.session_state.get("use_web", True),
                                            os.environ.get("GOOGLE_FACTCHECK_KEY", ""))
                finish(uid, "url", rep["claim_text"], rep, rep["source_url"])
            except security.UnsafeURL as e:
                st.error(str(e))
            except engine.SocialUnavailable as e:
                st.warning(str(e))
            except Exception:
                st.error("Could not verify that link. Try pasting the article text instead.")

    with t_soc:
        st.caption("Instagram, X and Facebook do not allow automatic reading of posts, so paste the "
                   "text or upload a screenshot. YouTube titles can be read automatically.")
        s_url = st.text_input("Post link (optional)", key="v_s_url")
        s_text = st.text_area("Or paste the post text", height=120, key="v_s_text")
        s_img = st.file_uploader("Or upload a screenshot", type=["jpg", "jpeg", "png"], key="v_s_img")
        if st.button("Verify post", type="primary", key="v_s_go"):
            try:
                if s_text.strip():
                    run_text(uid, s_text, "social", source_url=s_url.strip() or None, limits=[
                        "The text was pasted by the user. The original post was not accessed, so "
                        "we cannot confirm that it is real or who wrote it."])
                elif s_img:
                    text, err = engine.ocr_image(load_image(s_img))
                    if not text.strip():
                        st.warning("No readable text found in the screenshot. " + (f"({err})" if err else ""))
                    else:
                        run_text(uid, text, "social", limits=[
                            "Text was read from a user-supplied screenshot, which may be edited."])
                elif s_url.strip():
                    text, note = engine.fetch_social_text(s_url.strip())
                    run_text(uid, text, "social", source_url=s_url.strip(), limits=[note])
                else:
                    st.warning("Enter a link, paste text, or upload a screenshot.")
            except engine.SocialUnavailable as e:
                st.warning(str(e))
            except Exception as e:
                st.error(str(e) if isinstance(e, ValueError) else "Could not process that input.")

    if st.session_state.get("last_vid"):
        show_result(uid, st.session_state["last_vid"])


def page_history(user):
    uid = user["id"]
    st.markdown(hero("Records", "Verification History", "Every report you have run, with filters and export.", []), unsafe_allow_html=True)
    f1, f2, f3 = st.columns(3)
    search = f1.text_input("Search text")
    verdicts = f2.multiselect("Verdict", engine.VERDICTS)
    types = f3.multiselect("Input type", ["text", "image", "url", "social"])
    g1, g2 = st.columns(2)
    rng = g1.date_input("Date range", value=(), key="hist_dates")
    sorts = {"Newest first": "id DESC", "Oldest first": "id ASC", "Verdict A-Z": "verdict ASC, id DESC"}
    order = sorts[g2.selectbox("Sort", list(sorts))]

    q, args = ("SELECT id, report_id, created_at, input_type, verdict, basis, method, reason, source_url, "
               "content FROM verifications WHERE user_id=?"), [uid]
    if search.strip():
        q += " AND content LIKE ?"
        args.append(f"%{search.strip()}%")
    if verdicts:
        q += f" AND verdict IN ({','.join('?' * len(verdicts))})"
        args += verdicts
    if types:
        q += f" AND input_type IN ({','.join('?' * len(types))})"
        args += types
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        q += " AND created_at >= ? AND created_at < ?"
        args += [rng[0].strftime("%Y-%m-%d"), (rng[1] + timedelta(days=1)).strftime("%Y-%m-%d")]
    q += f" ORDER BY {order} LIMIT 500"      # `order` comes only from the fixed dict above
    with db() as c:
        rows = [dict(r) for r in c.execute(q, args)]
    if not rows:
        st.info("No reports match. Run a verification, or loosen the filters.")
        return
    df = pd.DataFrame(rows)
    show = df[["report_id", "created_at", "input_type", "verdict", "content"]].copy()
    show["created_at"] = show["created_at"].map(local_ts)
    st.dataframe(show, hide_index=True)
    safe = pd.DataFrame([{k: csv_safe(v) for k, v in r.items() if k != "id"} for r in rows])
    st.download_button("Export CSV", safe.to_csv(index=False).encode("utf-8"),
                       file_name="truthsync_history.csv", mime="text/csv")
    labels = {f"{r['report_id']} - {r['verdict']} - {r['content'][:50]}": r["id"] for r in rows}
    pick = st.selectbox("Open a report", list(labels))
    vid = labels[pick]
    with db() as c:
        rep = store.get_report(c, uid, vid)
    if rep:
        render_report(rep)
        send_panel(uid, vid)
        st.divider()
        if st.checkbox("I want to delete this report permanently", key=f"delchk{vid}"):
            if st.button("Delete report", key=f"del{vid}"):
                with db() as c:
                    c.execute("DELETE FROM verifications WHERE id=? AND user_id=?", (vid, uid))
                    audit(c, uid, "report_deleted", rep["report_id"])
                st.rerun()


def page_analytics(user):
    import plotly.express as px
    uid = user["id"]
    st.markdown(hero("Insights", "Analytics", "Verdict trends and device delivery statistics.", []), unsafe_allow_html=True)
    a1, a2, a3 = st.columns(3)
    rng = a1.date_input("Date range", value=(date.today() - timedelta(days=30), date.today()), key="an_dates")
    verdicts = a2.multiselect("Verdict", engine.VERDICTS, key="an_v")
    types = a3.multiselect("Input type", ["text", "image", "url", "social"], key="an_t")
    q, args = "SELECT created_at, input_type, verdict FROM verifications WHERE user_id=?", [uid]
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        q += " AND created_at >= ? AND created_at < ?"
        args += [rng[0].strftime("%Y-%m-%d"), (rng[1] + timedelta(days=1)).strftime("%Y-%m-%d")]
    if verdicts:
        q += f" AND verdict IN ({','.join('?' * len(verdicts))})"
        args += verdicts
    if types:
        q += f" AND input_type IN ({','.join('?' * len(types))})"
        args += types
    with db() as c:
        vrows = [dict(r) for r in c.execute(q, args)]
        drows = [dict(r) for r in c.execute(
            "SELECT dl.status, dl.created_at, dl.acked_at, d.name FROM deliveries dl JOIN devices d "
            "ON d.id=dl.device_pk WHERE d.user_id=?", (uid,))]
        hb = [dict(r) for r in c.execute(
            "SELECT substr(h.at,1,10) day, d.name, COUNT(*) n FROM heartbeats h JOIN devices d ON "
            "d.id=h.device_pk WHERE d.user_id=? GROUP BY day, d.name ORDER BY day", (uid,))]

    st.markdown(section("Verifications"), unsafe_allow_html=True)
    if not vrows:
        st.info("No verifications in this range yet.")
    else:
        df = pd.DataFrame(vrows)
        df["created_at"] = pd.to_datetime(df["created_at"])
        c1, c2 = st.columns(2)
        vc = df["verdict"].value_counts().reset_index()
        vc.columns = ["verdict", "count"]
        c1.plotly_chart(plotly_dark(px.pie(vc, names="verdict", values="count", hole=.5, color="verdict",
                                           color_discrete_map=VERDICT_COLORS, title="Verdict distribution")))
        tc = df["input_type"].value_counts().reset_index()
        tc.columns = ["type", "count"]
        c2.plotly_chart(plotly_dark(px.bar(tc, x="type", y="count", title="Input types")))
        gran = st.radio("Counts per", ["Day", "Week"], horizontal=True)
        series = df.set_index("created_at").resample("D" if gran == "Day" else "W").size().reset_index(name="count")
        st.plotly_chart(plotly_dark(px.bar(series, x="created_at", y="count", title=f"Verifications per {gran.lower()}")))
    st.caption("A confidence histogram is intentionally not shown: the engine does not produce "
               "calibrated confidence scores.")

    st.markdown(section("Devices and deliveries"), unsafe_allow_html=True)
    if not drows:
        st.info("No device messages yet.")
    else:
        dd = pd.DataFrame(drows)
        sc = dd["status"].value_counts().reset_index()
        sc.columns = ["status", "count"]
        d1, d2 = st.columns(2)
        d1.plotly_chart(plotly_dark(px.bar(sc, x="status", y="count", title="Delivery status (pending, sent, displayed, failed, expired)")))
        acked = dd.dropna(subset=["acked_at"]).copy()
        if len(acked):
            acked["secs"] = (pd.to_datetime(acked["acked_at"]) - pd.to_datetime(acked["created_at"])).dt.total_seconds()
            d2.plotly_chart(plotly_dark(px.histogram(acked, x="secs", nbins=20, title="Seconds until the OLED confirmed")))
        else:
            d2.info("No acknowledgements yet.")
    if hb:
        st.plotly_chart(plotly_dark(px.bar(pd.DataFrame(hb), x="day", y="n", color="name",
                                           title="Device heartbeats per day (activity history)")))
    else:
        st.caption("Heartbeat history appears once a device has connected.")


def page_devices(user):
    uid = user["id"]
    st.markdown(hero("Hardware", "Device Management", "Register ESP32 + OLED displays and send verdicts to them in real time.", ["ESP32","SSD1306 OLED","SDA 26","SCL 27"]), unsafe_allow_html=True)
    with db() as c:
        devices.sweep(c)
        rows = c.execute("SELECT * FROM devices WHERE user_id=? ORDER BY revoked, name", (uid,)).fetchall()
    api_base = os.environ.get("API_BASE_URL", "http://YOUR-PC-IP:8000")
    st.markdown(f'<div class="ts-note">Your ESP32 talks to the <b>device API</b> at '
                f'<code>{esc(api_base)}</code> (a separate program - see README). Put this address, '
                f'the Device ID and the API key into the settings block at the top of <code>esp32_oled_final.ino</code>.</div>',
                unsafe_allow_html=True)

    cred = st.session_state.get("new_cred")
    if cred:
        st.success("Device registered. Copy the API key NOW - it is shown only once and only its "
                   "hash is stored.")
        st.code(f"DEVICE_ID  = {cred[0]}\nDEVICE_KEY = {cred[1]}")
        if st.button("I have saved the key"):
            st.session_state.pop("new_cred", None)
            st.rerun()

    with st.expander("Register a new device", expanded=not rows):
        with st.form("regdev"):
            name = st.text_input("Device name", placeholder="Desk ESP32")
            dtype = st.selectbox("Device type", ["ESP32 with OLED (SSD1306)", "ESP32",
                                                 "Other compatible microcontroller"])
            if st.form_submit_button("Register device", type="primary"):
                try:
                    with db() as c:
                        did, key = devices.register_device(c, uid, name, dtype)
                    st.session_state["new_cred"] = (did, key)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    if not rows:
        st.info("No devices yet. Register your first ESP32 above.")
        return
    for d in rows:
        online = devices.is_online(d["last_seen"]) and not d["revoked"]
        title = f"{d['name']}  -  {'REVOKED' if d['revoked'] else ('Online' if online else 'Offline')}"
        with st.expander(title + ("  (default)" if d["is_default"] else "")):
            st.markdown(f"{status_dot(online)} &nbsp; type: **{esc(d['device_type'])}** &nbsp; ID: "
                        f"`{d['device_id']}` &nbsp; last seen: {esc(local_ts(d['last_seen']) if d['last_seen'] else 'never')}",
                        unsafe_allow_html=True)
            if d["revoked"]:
                st.caption("Revoked: this device can no longer fetch messages.")
            else:
                c1, c2, c3 = st.columns(3)
                new_name = c1.text_input("Rename", value=d["name"], key=f"rn{d['id']}")
                if c1.button("Save name", key=f"rnb{d['id']}") and new_name.strip():
                    with db() as c:
                        c.execute("UPDATE devices SET name=? WHERE id=? AND user_id=?",
                                  (new_name.strip()[:40], d["id"], uid))
                    st.rerun()
                if c2.button("Send test message", key=f"tm{d['id']}"):
                    with db() as c:
                        devices.queue_test_message(c, uid, d["id"])
                    st.success("Test message queued. It becomes 'displayed' only after the ESP32 confirms.")
                if c2.button("Make default", key=f"df{d['id']}"):
                    with db() as c:
                        c.execute("UPDATE devices SET is_default=0 WHERE user_id=?", (uid,))
                        c.execute("UPDATE devices SET is_default=1 WHERE id=? AND user_id=?", (d["id"], uid))
                    st.rerun()
                if c3.button("Revoke access", key=f"rv{d['id']}"):
                    with db() as c:
                        c.execute("UPDATE devices SET revoked=1, is_default=0 WHERE id=? AND user_id=?", (d["id"], uid))
                        audit(c, uid, "device_revoked", d["device_id"])
                    st.rerun()
            with db() as c:
                pend = c.execute("SELECT COUNT(*) FROM deliveries WHERE device_pk=? AND status IN "
                                 "('pending','sent')", (d["id"],)).fetchone()[0]
            if pend and not d["revoked"]:
                st.caption(f"{pend} message(s) pending - revoke the device before deleting it.")
            elif st.checkbox("Delete this device and its history", key=f"dc{d['id']}"):
                if st.button("Delete device", key=f"dd{d['id']}"):
                    with db() as c:
                        c.execute("DELETE FROM devices WHERE id=? AND user_id=?", (d["id"], uid))
                        audit(c, uid, "device_deleted", d["device_id"])
                    st.rerun()

    st.markdown(section("Delivery history"), unsafe_allow_html=True)
    if st.button("Refresh status"):
        st.rerun()
    with db() as c:
        dl = [dict(r) for r in c.execute(
            "SELECT dl.created_at, d.name AS device, dl.kind, v.report_id, dl.status, dl.attempts, "
            "dl.sent_at, dl.acked_at FROM deliveries dl JOIN devices d ON d.id=dl.device_pk "
            "LEFT JOIN verifications v ON v.id=dl.verification_id WHERE d.user_id=? "
            "ORDER BY dl.id DESC LIMIT 50", (uid,))]
    if dl:
        ddf = pd.DataFrame(dl)
        for col in ("created_at", "sent_at", "acked_at"):
            ddf[col] = ddf[col].map(lambda v: local_ts(v) if v else v)
        st.dataframe(ddf, hide_index=True)
    else:
        st.caption("No messages sent yet.")


def page_notifications(user):
    uid = user["id"]
    st.markdown(hero("Alerts", "Notifications", "Delivery confirmations and system messages.", []), unsafe_allow_html=True)
    with db() as c:
        devices.sweep(c)
        rows = c.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 60", (uid,)).fetchall()
    if not rows:
        st.info("You're all caught up. Notifications appear after verifications and device events.")
        return
    if st.button("Mark all as read"):
        with db() as c:
            c.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (uid,))
        st.rerun()
    for n in rows:
        a, b = st.columns([6, 1])
        a.markdown(f"{'' if n['is_read'] else '**NEW** '}{esc(n['message'])} &nbsp;"
                   f"<span class='ts-muted'>{esc(n['kind'])} &middot; {esc(local_ts(n['created_at']))}</span>",
                   unsafe_allow_html=True)
        if not n["is_read"] and b.button("Read", key=f"nr{n['id']}"):
            with db() as c:
                c.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (n["id"], uid))
            st.rerun()


def page_profile(user):
    uid = user["id"]
    st.markdown(hero("Account", "Profile & Settings", "Manage your details and password.", []), unsafe_allow_html=True)
    st.markdown(f"**Email:** {esc(user['email'])} &nbsp; **Role:** {esc(user['role'])}", unsafe_allow_html=True)
    with st.form("prof"):
        name = st.text_input("Name", value=user["name"])
        if st.form_submit_button("Save profile") and name.strip():
            with db() as c:
                c.execute("UPDATE users SET name=? WHERE id=?", (name.strip()[:60], uid))
            st.success("Saved.")
    with st.form("pw"):
        old = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        new2 = st.text_input("Repeat new password", type="password")
        if st.form_submit_button("Change password"):
            problem = security.password_problem(new)
            if not security.verify_password(old, user["pw_hash"]):
                st.error("Current password is wrong.")
            elif problem:
                st.error(problem)
            elif new != new2:
                st.error("The new passwords do not match.")
            else:
                with db() as c:
                    c.execute("UPDATE users SET pw_hash=? WHERE id=?", (security.hash_password(new), uid))
                    audit(c, uid, "password_changed", "")
                    notify(c, uid, "security", "Your password was changed.")
                st.success("Password changed.")
    st.caption("Theme: this build ships a dark theme only (see .streamlit/config.toml).")


def page_admin(user):
    if user["role"] != "admin":                       # enforced on the server, not just hidden
        st.error("You are not allowed to view this page.")
        return
    st.markdown(hero("Admin", "Admin Dashboard", "Users, system health and audit log.", ["Admin only"]), unsafe_allow_html=True)
    with db() as c:
        devices.sweep(c)
        n = lambda q: c.execute(q).fetchone()[0]       # noqa: E731
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(TS_FMT)
        active = c.execute("SELECT COUNT(DISTINCT user_id) FROM audit_events WHERE action='login_ok' "
                           "AND created_at>=?", (since,)).fetchone()[0]
        devs = c.execute("SELECT last_seen FROM devices WHERE revoked=0").fetchall()
        online = sum(1 for d in devs if devices.is_online(d["last_seen"]))
        stats = dict(users=n("SELECT COUNT(*) FROM users"), ver=n("SELECT COUNT(*) FROM verifications"),
                     dev=len(devs), ok=n("SELECT COUNT(*) FROM deliveries WHERE status='displayed'"),
                     bad=n("SELECT COUNT(*) FROM deliveries WHERE status IN ('failed','expired')"))
        users = [dict(r) for r in c.execute("SELECT id,email,name,role,is_active,created_at FROM users ORDER BY id")]
        audits = [dict(r) for r in c.execute("SELECT created_at,user_id,action,detail FROM audit_events ORDER BY id DESC LIMIT 100")]
        errors = [dict(r) for r in c.execute("SELECT created_at,detail FROM audit_events WHERE action='error' ORDER BY id DESC LIMIT 20")]
    metrics_row([("Users", stats["users"]), ("Active (7 days)", active), ("Verifications", stats["ver"]),
                 ("Devices", stats["dev"]), ("Online", online)])
    st.write("")
    metrics_row([("Offline", stats["dev"] - online), ("Delivered", stats["ok"]), ("Failed/expired", stats["bad"])])

    st.markdown(section("Users"), unsafe_allow_html=True)
    st.caption("Only account details are shown - never users' submitted content.")
    st.dataframe(pd.DataFrame(users), hide_index=True)
    others = {f"{u['email']} ({'active' if u['is_active'] else 'disabled'})": u for u in users if u["id"] != user["id"]}
    if others:
        pick = others[st.selectbox("Enable / disable an account", list(others))]
        if st.button("Toggle active"):
            with db() as c:
                c.execute("UPDATE users SET is_active=? WHERE id=?", (0 if pick["is_active"] else 1, pick["id"]))
                audit(c, user["id"], "admin_toggle_user", pick["email"])
            st.rerun()

    st.markdown(section("System health & configuration"), unsafe_allow_html=True)
    try:
        r = requests.get(os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/health", timeout=3)
        api_ok = r.status_code == 200
    except Exception:
        api_ok = False
    cfg = {"Device API reachable": api_ok, "Email (SMTP) configured": mailer.smtp_configured(),
           "Google Fact Check key set": bool(os.environ.get("GOOGLE_FACTCHECK_KEY")),
           "OCR.space key set": bool(os.environ.get("OCR_SPACE_KEY")),
           "ADMIN_EMAIL set": bool(os.environ.get("ADMIN_EMAIL")),
           "DEV_MODE on (must be OFF in production)": os.environ.get("DEV_MODE") == "1"}
    for k, v in cfg.items():
        st.markdown(f"{'🟢' if v else '⚪'} {k}")
    st.markdown(section("Recent errors"), unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(errors), hide_index=True) if errors else st.caption("None recorded.")
    st.markdown(section("Audit log"), unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(audits), hide_index=True)


def page_help(user):
    st.markdown(hero("Guide", "Help & Documentation", "How TruthSync works and how to connect your device.", []), unsafe_allow_html=True)
    st.markdown("""
**How it works.** You submit text, an image, a link or a social post. TruthSync checks curated facts,
then searches the web / fact-check sites, and returns one of four verdicts with its sources.

**Verdicts.** *Likely fake* / *Likely real* mean sources lean that way - not that it is proven.
*Unverified* means evidence was mixed or thin. *Insufficient information* means nothing usable was found.

**Assessment types.** *Evidence-based* (sources compared), *Curated* (an entry in `facts.py`),
*Model prediction* (writing style only - never treat as a fact check).

**OLED display.** Register your ESP32 under Device Management, flash the firmware with the Device ID
and key, then send a test message. A message shows **Displayed** only after the ESP32 confirms it.

**Not included in this version.** Video verification, PDF report download, light theme.
Images are not stored - only the extracted text is kept.
""")


# ================================================================== main
def main():
    user = current_user()
    if not user:
        auth_page()
        return
    with db() as c:
        unread = c.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
                           (user["id"],)).fetchone()[0]
    allowed = [p for p in PAGES if p[0] != "admin" or user["role"] == "admin"]
    labels = dict(allowed)
    with st.sidebar:
        st.markdown(logo(), unsafe_allow_html=True)
        page = st.radio("Navigate", [p[0] for p in allowed], label_visibility="collapsed",
                        format_func=lambda k: f":material/{PAGE_ICON[k]}: " + labels[k]
                        + (f"  ({unread})" if k == "notifications" and unread else ""))
        st.markdown(display_link(), unsafe_allow_html=True)
        st.divider()
        st.caption(f"Signed in as {user['email']}")
        if st.button("Sign out"):
            with db() as c:
                audit(c, user["id"], "logout", "")
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
    {"overview": page_overview, "verify": page_verify, "history": page_history,
     "analytics": page_analytics, "devices": page_devices, "notifications": page_notifications,
     "profile": page_profile, "admin": page_admin, "help": page_help}[page](user)


main()
