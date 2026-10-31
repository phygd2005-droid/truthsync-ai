"""Passwords, device keys, SSRF-safe URL fetching and article extraction."""
import hashlib
import hmac
import ipaddress
import re
import secrets
import socket
from urllib.parse import urljoin, urlparse

import requests

# ------------------------------------------------------------------ passwords
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(email):
    return bool(email) and len(email) <= 254 and bool(_EMAIL_RE.match(email))


def hash_password(password):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(password, stored):
    try:
        scheme, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                           n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(h.hex(), hash_hex)
    except Exception:
        return False


def password_problem(password):
    """Returns a message if the password is too weak, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if password.lower() == password or not any(ch.isdigit() for ch in password):
        return "Use a mix of upper/lower case letters and at least one number."
    return None


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


# ------------------------------------------------------------------ device keys
def new_device_credentials():
    """Returns (device_id, api_key, key_hash). The api_key is shown ONCE and never stored."""
    device_id = "esp32_" + secrets.token_hex(5)
    api_key = "tsk_" + secrets.token_urlsafe(32)
    return device_id, api_key, hash_token(api_key)


def check_key(api_key, key_hash):
    return hmac.compare_digest(hash_token(api_key or ""), key_hash or "")


# ------------------------------------------------------------------ SSRF protection
class UnsafeURL(Exception):
    pass


def _ip_is_public(ip_str):
    ip = ipaddress.ip_address(ip_str)
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_url(url):
    """Raises UnsafeURL unless the URL is plain http(s) to a public internet host."""
    if not url or len(url) > 2000:
        raise UnsafeURL("Please enter a valid URL.")
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https"):
        raise UnsafeURL("Only http:// and https:// links are allowed.")
    if p.username or p.password:
        raise UnsafeURL("Links containing a username/password are not allowed.")
    host = p.hostname
    if not host:
        raise UnsafeURL("The link has no host name.")
    try:
        port = p.port
    except ValueError:
        raise UnsafeURL("Invalid port in link.")
    if port not in (None, 80, 443):
        raise UnsafeURL("Only the standard web ports (80/443) are allowed.")
    try:
        infos = socket.getaddrinfo(host, port or (443 if p.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise UnsafeURL("Could not find that website (DNS lookup failed).")
    for info in infos:
        if not _ip_is_public(info[4][0]):
            raise UnsafeURL("That address points to a private or internal network, "
                            "so it was blocked for safety.")
    return url.strip()


def safe_fetch(url, max_bytes=1_500_000, timeout=8, max_redirects=3):
    """Fetch a public web page with timeouts, a size cap and redirect re-validation.
    Returns dict(url, status, content_type, text, truncated).
    Known limit: DNS is checked before the request; a hostile DNS server could in theory
    change its answer between the check and the request (DNS rebinding)."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TruthSyncBot/1.0)",
               "Accept": "text/html,application/xhtml+xml"}
    current = url
    for _ in range(max_redirects + 1):
        check_url(current)
        try:
            r = requests.get(current, headers=headers, timeout=timeout, stream=True,
                             allow_redirects=False)
        except requests.RequestException as e:
            raise UnsafeURL(f"Could not download the page ({type(e).__name__}).")
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            current = urljoin(current, r.headers["Location"])
            r.close()
            continue
        ctype = r.headers.get("Content-Type", "")
        if "html" not in ctype.lower() and "text" not in ctype.lower():
            r.close()
            raise UnsafeURL("That link is not a web page (content type: "
                            f"{ctype or 'unknown'}).")
        data, truncated = b"", False
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) >= max_bytes:
                truncated = True
                data = data[:max_bytes]
                break
        r.close()
        enc = r.encoding or "utf-8"
        return {"url": current, "status": r.status_code, "content_type": ctype,
                "text": data.decode(enc, errors="replace"), "truncated": truncated}
    raise UnsafeURL("Too many redirects.")


def extract_article(html):
    """Returns dict(title, text, published). Uses only the page's own HTML."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    def meta(*names):
        for n in names:
            tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return ""

    title = meta("og:title", "twitter:title") or (soup.title.string.strip()
                                                  if soup.title and soup.title.string else "")
    published = meta("article:published_time", "datePublished", "date")
    for t in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        t.decompose()
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    paras = [p for p in paras if len(p.split()) >= 6]
    return {"title": title, "text": " ".join(paras), "published": published}
