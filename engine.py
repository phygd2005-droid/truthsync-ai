"""Verification engine. Reuses the original project's verifier.py, facts.py and model.pkl.

Verdicts: LIKELY FAKE / LIKELY REAL / UNVERIFIED / INSUFFICIENT INFORMATION
`basis` says what the verdict rests on:
  evidence -> web / fact-check evidence was found and compared
  curated  -> an entry in facts.py (hand-written by the project owner)
  model    -> only the writing-style classifier (NOT a fact check)
"""
import io
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from common import clean
from facts import check_facts
from verifier import verify_text

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE, REAL, UNVER, INSUFF = "LIKELY FAKE", "LIKELY REAL", "UNVERIFIED", "INSUFFICIENT INFORMATION"
VERDICTS = [FAKE, REAL, UNVER, INSUFF]
MAP = {"FAKE": FAKE, "TRUE": REAL, "UNCERTAIN": UNVER}

_CONTRA = ("false", "fake", "denies", "contradict", "debunk", "incorrect", "misleading",
           "hoax", "not true")
_SUPPORT = ("support", "true", "reports the death", "correct", "accurate")


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def normalize(text, limit=5000):
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def host_of(url):
    h = (urlparse(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


# ------------------------------------------------------------------ model (fallback only)
_model = None


def ml_style_check(text):
    global _model
    try:
        if _model is None:
            import joblib
            _model = joblib.load(os.path.join(HERE, "model.pkl"))
        proba = _model.predict_proba([clean(text)])[0]          # [fake, true]
    except Exception:
        return None, 0.0
    return ("TRUE" if proba[1] >= 0.5 else "FAKE"), float(max(proba)) * 100


# ------------------------------------------------------------------ OCR
_reader = None


def ocr_image(img):
    """Returns (text, error). Uses EasyOCR when installed, else the free OCR.space API."""
    global _reader
    try:
        import easyocr
        import numpy as np
        if _reader is None:
            _reader = easyocr.Reader(["en"])
        return " ".join(_reader.readtext(np.array(img), detail=0)), ""
    except ImportError:
        pass
    key = os.environ.get("OCR_SPACE_KEY", "helloworld")   # free key: https://ocr.space/ocrapi
    im = img.copy()
    im.thumbnail((1400, 1400))
    quality = 85
    while True:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=quality)
        if buf.tell() < 1_000_000 or quality <= 40:
            break
        quality -= 15
    try:
        r = requests.post("https://api.ocr.space/parse/image",
                          files={"file": ("image.jpg", buf.getvalue(), "image/jpeg")},
                          data={"apikey": key, "language": "eng", "OCREngine": "2"},
                          timeout=40).json()
        if r.get("IsErroredOnProcessing"):
            return "", str(r.get("ErrorMessage"))
        return " ".join(p.get("ParsedText", "") for p in r.get("ParsedResults", [])), ""
    except Exception as e:
        return "", f"OCR service unreachable ({type(e).__name__})"


# ------------------------------------------------------------------ evidence bucketing
def bucket_evidence(items):
    sup, con, rel = [], [], []
    for e in items or []:
        st = (e.get("stance") or "").lower()
        row = {"title": e.get("title", ""), "url": e.get("url", ""), "stance": e.get("stance", "")}
        if any(w in st for w in _CONTRA):
            con.append(row)
        elif any(w in st for w in _SUPPORT):
            sup.append(row)
        else:
            rel.append(row)
    return sup, con, rel


def postprocess(report, source_url=None):
    """Pure function: applies honesty rules to a finished report dict."""
    host = host_of(source_url)
    if host:
        for bucket in ("supporting", "contradicting", "related"):
            for e in report[bucket]:
                if host_of(e["url"]) == host:
                    e["stance"] += " (same website as submitted link - not independent)"
        independent = [e for e in report["supporting"] if host_of(e["url"]) != host]
        if report["verdict"] == REAL and report["supporting"] and not independent:
            report["verdict"] = UNVER
            report["reason"] = ("Only the submitted website itself supports this claim; "
                                "no independent source was found.")
    return report


# ------------------------------------------------------------------ main entry point
def verify_content(text, input_type="text", use_web=True, google_key="", source_url=None,
                   extra_limitations=None):
    text = normalize(text)
    limitations = list(extra_limitations or [])
    limitations.append("An automated assessment is not established fact. "
                       "Check the listed sources yourself before sharing.")
    report = {"verdict": INSUFF, "basis": "none", "confidence": None,
              "method": "-", "reason": "", "claims": [], "supporting": [],
              "contradicting": [], "related": [], "limitations": limitations,
              "retrieved_at": utcnow()}

    if len(text.split()) < 4:
        report.update(verdict=INSUFF, method="Input check",
                      reason="The text is too short to contain a checkable claim.")
        return report

    # Layer 1: hand-written facts (facts.py)
    v, why = check_facts(text)
    if v:
        report.update(verdict=MAP[v], basis="curated", method="Curated fact entry (facts.py)",
                      reason=why, claims=[text[:300]])
        limitations.append("This verdict comes from an entry written by the project owner, "
                           "not from live sources.")
        return postprocess(report, source_url)

    # Layer 2: online evidence
    res = None
    if use_web:
        try:
            res = verify_text(text, google_key)
        except Exception as e:
            limitations.append(f"Online check failed ({type(e).__name__}).")
    else:
        limitations.append("Online evidence search was switched off.")

    if res:
        sup, con, rel = bucket_evidence(res.get("evidence"))
        report.update(supporting=sup, contradicting=con, related=rel,
                      claims=[c.get("claim", "") for c in res.get("claims", [])] or [text[:300]],
                      method="Web search + fact-check sites (verifier.py)",
                      reason=res.get("reason", ""))
        dbg = res.get("debug") or {}
        if res["verdict"] != "UNCERTAIN":
            report.update(verdict=MAP[res["verdict"]], basis="evidence")
            limitations.append("Source agreement is a heuristic score, not a calibrated "
                               "probability, so no confidence percentage is shown.")
            return postprocess(report, source_url)
        no_results = (dbg.get("search_results", 0) == 0) and not (sup or con or rel)
        report["verdict"] = INSUFF if no_results else UNVER
        if no_results:
            limitations.append("No search results were returned (offline, rate-limited or "
                               "no coverage).")
    else:
        report["verdict"] = INSUFF if not use_web else UNVER
        report["claims"] = [text[:300]]
        report["reason"] = report["reason"] or "No online evidence was available."

    # Layer 3: writing-style model, last resort, clearly labelled
    mv, mc = ml_style_check(text)
    if mv and mc >= 80:
        lean = "real" if mv == "TRUE" else "fake"
        report.update(verdict=UNVER, basis="model",
                      method="Writing-style classifier (model prediction only)",
                      reason=f"No usable evidence was found, so no verdict is given. A classifier that "
                             f"judges writing style only leans '{lean}' ({mc:.0f}% model score); it does "
                             f"not check facts. Paste the full headline or article text, or check the "
                             f"sources yourself.")
        limitations.append("Model prediction only: it judges writing style, not truth, so it is "
                           "never shown as a verdict.")
    return postprocess(report, source_url)



# ------------------------------------------------------------------ URL and social inputs
def clean_headline(title):
    """Remove site names and 'live updates' noise so the search query is just the claim."""
    t = re.split(r"\s[|\u2013\u2014-]\s(?=[A-Z][\w .]{2,30}$)", str(title or "").strip())[0]
    t = re.sub(r"(?i)\b(live updates?|live blog|live|updates?)\b[:\s]*", "", t)
    return re.sub(r"\s+", " ", t).strip(" :-|")


def verify_url(url, use_web=True, google_key=""):
    from security import safe_fetch, extract_article
    h = host_of(url)
    if any(h == x or h.endswith("." + x) for x in ("instagram.com", "facebook.com", "fb.com", "x.com",
                                                   "twitter.com", "tiktok.com")):
        # These sites return a login page to programs; checking that page gives a meaningless verdict.
        raise SocialUnavailable("Instagram, Facebook, X and TikTok links cannot be read automatically. "
                                "Copy the post's caption or headline and paste it in the Text tab "
                                "(or upload a screenshot in Image / Social media).")
    page = safe_fetch(url)
    art = extract_article(page["text"])
    limits = [f"Page fetched from {page['url']} (HTTP {page['status']})."]
    if page["truncated"]:
        limits.append("The page was larger than the size limit and was cut off.")
    lead = art["text"][:600]
    if len(art["text"]) < 200:
        limits.append("Very little article text was found (the page may need JavaScript, "
                      "be paywalled, or not be an article). Only the headline was checked.")
    claim = clean_headline(art["title"]) if art["title"] else ""
    if len(claim.split()) < 5:                      # headline too short or missing: use the lead
        claim = (claim + ". " + lead[:250]).strip(". ")
    rep = verify_content(claim, "url", use_web, google_key, source_url=page["url"],
                         extra_limitations=limits)
    rep["source_url"] = page["url"]
    rep["page_title"] = art["title"]
    rep["published"] = art["published"]
    rep["claim_text"] = claim
    return rep


SOCIAL_HOSTS = ("instagram.com", "youtube.com", "youtu.be", "x.com", "twitter.com",
                "facebook.com", "fb.com")


class SocialUnavailable(Exception):
    pass


def fetch_social_text(url):
    """Returns (text, note). Only YouTube titles are readable without logging in (oEmbed).
    Instagram, X and Facebook block automated reading, so the user must paste the text."""
    host = host_of(url)
    if not any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS):
        raise SocialUnavailable("That is not a supported social media link "
                                "(Instagram, YouTube, X, Facebook).")
    if host in ("youtube.com", "m.youtube.com", "youtu.be") or host.endswith(".youtube.com"):
        try:
            r = requests.get("https://www.youtube.com/oembed",
                             params={"url": url, "format": "json"}, timeout=8)
            if r.status_code == 200:
                j = r.json()
                return (j.get("title", ""),
                        f"Title read from YouTube's public oEmbed service (channel: "
                        f"{j.get('author_name', 'unknown')}). The video itself was not analysed.")
        except Exception:
            pass
        raise SocialUnavailable("YouTube did not return public details for this link. "
                                "Paste the claim text below instead.")
    raise SocialUnavailable("This platform does not allow automatic reading of posts. "
                            "Paste the post text (or upload a screenshot) instead.")
