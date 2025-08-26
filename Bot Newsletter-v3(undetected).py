# by achraf48.co — telegram: https://t.me/ouchen2
import os
import sys
import time
import random
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlsplit, quote_plus
import threading
import imaplib
import email as email_pkg
import re

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer, QEventLoop
from PyQt5.QtGui import QFont, QPalette, QColor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QSpinBox,
    QCheckBox, QComboBox, QFileDialog, QMessageBox,
    QProgressBar, QGroupBox, QGridLayout
)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options as COptions
from selenium.webdriver.firefox.options import Options as FOptions
from selenium.webdriver.edge.options import Options as EOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, ElementClickInterceptedException,
    NoSuchElementException, StaleElementReferenceException
)

# webdriver-manager services (used as fallback)
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# try undetected_chromedriver for Chrome
try:
    import undetected_chromedriver as uc
except Exception:
    uc = None

from faker import Faker
fake = Faker()

# ---------- CONFIG ----------
DORKS = [
    # Core phrases
    'intitle:newsletter (subscribe OR "sign up")',
    'inurl:newsletter (subscribe OR signup)',
    '"subscribe to our newsletter" -site:facebook.com -site:twitter.com',
    '"join our newsletter" (footer OR subscribe)',
    '"get updates" (newsletter OR email) -site:facebook.com -site:twitter.com',
    '"sign up for our newsletter" -site:facebook.com -site:twitter.com',
    '"newsletter signup" inurl:subscribe',
    '"subscribe to receive updates" (newsletter OR email)',
    '"subscribe for exclusive updates" (newsletter OR offers)',
    '"enter your email" (newsletter OR subscribe)',
    '"weekly newsletter" (subscribe OR sign up)',
    '"join our mailing list" -site:linkedin.com',
    '"subscribe to our mailing list" -site:pinterest.com',
    '"get the latest news" (newsletter OR email)',
    '"email updates" (subscribe OR sign up)',
    '"free newsletter" (join OR subscribe)',
    '"newsletter form" inurl:subscribe',
    '"stay informed" (newsletter OR email updates)',
    '"sign up for email alerts" -site:facebook.com -site:twitter.com',
    '"exclusive newsletter" (sign up OR subscribe)',

    # Variations on "mailing list"
    '"join our email list" -site:facebook.com',
    '"subscribe to email list" -site:twitter.com',
    '"sign up for our mailing list" -site:instagram.com',
    '"subscribe for email updates" -site:youtube.com',
    '"join our list" (newsletter OR updates)',

    # Using intitle/inurl for deeper matches
    'intitle:"sign up" "newsletter"',
    'intitle:"subscribe" "newsletter"',
    'inurl:subscribe-newsletter',
    'inurl:newsletter-signup',
    'inurl:join-newsletter',
    'inurl:newsletter/register',
    'inurl:newsletter-subscribe',
    'intitle:"email newsletter" subscribe',
    'intitle:"newsletter" "sign up today"',
    'inurl:/newsletter/subscribe',
    'inurl:/newsletter/signup',

    # Contextual clues
    '"subscribe for news and updates"',
    '"sign up for free updates"',
    '"subscribe now" "newsletter"',
    '"join the newsletter" footer',
    '"subscribe for our latest news"',
    '"sign up to get updates"',
    '"newsletter subscription form"',
    '"opt in for newsletter"',
    '"newsletter opt-in" subscribe',
    '"receive our newsletter by email"',

    # Marketing / e-commerce variations
    '"exclusive offers" "newsletter signup"',
    '"special offers" "sign up for newsletter"',
    '"discount newsletter" "subscribe"',
    '"sign up for deals" newsletter',
    '"vip newsletter" subscribe',
    '"get exclusive deals" newsletter',
    '"members only newsletter" sign up',
    '"subscriber newsletter" join now',
    '"newsletter benefits" sign up',
    '"early access" "newsletter signup"',

    # Other call-to-actions
    '"be the first to know" newsletter',
    '"never miss an update" subscribe',
    '"latest articles" newsletter signup',
    '"company newsletter" sign up',
    '"stay up to date" newsletter',
    '"insider newsletter" subscribe',
    '"join the community" newsletter',
    '"stay connected" email newsletter',
    '"industry newsletter" sign up',
    '"updates in your inbox" newsletter',

    # Filetype searches (uncommon trick)
    '"subscribe to our newsletter" filetype:pdf',
    '"join our mailing list" filetype:pdf',
    '"newsletter signup" filetype:docx',
    '"email updates" filetype:ppt',
    '"newsletter form" filetype:xls',

    # Exclusion-focused
    '"subscribe to newsletter" -facebook -twitter -linkedin',
    '"newsletter signup" -facebook -pinterest',
    '"sign up for newsletter" -site:youtube.com',
    '"join newsletter" -site:reddit.com',
    '"email newsletter" -site:medium.com',

    # Using OR groups
    '"sign up" OR "subscribe" "weekly newsletter"',
    '"newsletter" (join OR subscribe OR signup)',
    '"opt-in" OR "subscribe" "newsletter"',
    '"register" OR "subscribe" "newsletter"',
    '"get on the list" OR "join newsletter"',

    # Footer/header specific
    '"footer" "newsletter signup"',
    '"header" "subscribe newsletter"',
    '"sidebar" "newsletter form"',
    '"widget" "newsletter signup"',
    '"popup" "subscribe newsletter"',

    # Brand/news-specific
    '"company updates" newsletter',
    '"corporate newsletter" sign up',
    '"brand newsletter" subscribe',
    '"press newsletter" sign up',
    '"product newsletter" subscribe',

    # Geared toward organizations
    '"university newsletter" subscribe',
    '"school newsletter" sign up',
    '"church newsletter" subscribe',
    '"charity newsletter" sign up',
    '"ngo newsletter" subscribe',

    # Other opt-in wording
    '"sign up to our newsletter" "enter email"',
    '"newsletter signup" "email address"',
    '"join our newsletter" "first name"',
    '"subscribe to newsletter" "last name"',
    '"sign up now" "newsletter form"',

    # Miscellaneous
    '"weekly digest" subscribe',
    '"daily newsletter" sign up',
    '"monthly newsletter" join',
    '"company newsletter" updates',
    '"subscribe to our updates" newsletter',
    '"sign up for free newsletter" updates',
    '"join the club" newsletter',
    '"insider access" newsletter',
    '"subscriber only newsletter"',
    '"signup bonus" newsletter',
]


BLOCKED_DOMAINS_FILE = "skip_domains.txt"
SUCCESS_FILE = "success.txt"
FAILED_FILE = "failed.txt"
COOKIES_FILE = "google_cookies.json"
PROCESSED_FILE = "processed_emails.txt"
PROCESS_LOCK = threading.Lock()
# ---------------------------

def load_skip_domains() -> set:
    if not os.path.isfile(BLOCKED_DOMAINS_FILE):
        return set()
    with open(BLOCKED_DOMAINS_FILE, encoding="utf-8") as f:
        return {line.strip().lower() for line in f if line.strip()}

SKIP_DOMAINS = load_skip_domains()

def host_of(url: str) -> str:
    return urlparse(url).netloc.lower()

def is_blocked(url: str) -> bool:
    h = host_of(url)
    return any(b in h for b in SKIP_DOMAINS)

def timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")

def random_info() -> dict:
    return {
        "name": fake.name(),
        "first": fake.first_name(),
        "last": fake.last_name(),
        "email": fake.email(),
        "phone": fake.phone_number(),
        "address": fake.address().replace("\n", ", "),
        "city": fake.city(),
        "state": fake.state(),
        "zip": fake.zipcode(),
        "country": fake.country(),
        "company": fake.company(),
        "birthday": fake.date_of_birth(minimum_age=18, maximum_age=70).strftime("%m/%d/%Y"),
        "website": fake.url(),
        "job": fake.job(),
    }

def build_driver(browser: str, headless: bool):
    """
    Create a webdriver. For Chrome prefer undetected_chromedriver (uc) if available,
    else fall back to webdriver-manager + selenium.Chrome.
    """
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36")
    if browser.lower() == "chrome":
        opts = COptions()
        # headless flags (both for compatibility)
        if headless:
            opts.add_argument("--headless=new")
            opts.add_argument("--headless")
        opts.add_argument("--window-size=1280,800")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument(f"--user-agent={ua}")

        # Try undetected_chromedriver first
        if uc is not None:
            try:
                # uc accepts a ChromeOptions instance; pass options
                # Note: some uc versions have different signatures; keep simple
                return uc.Chrome(options=opts)
            except Exception as e:
                # Fall back to selenium if uc failed
                print(f"[build_driver] uc.Chrome() failed: {e}; falling back to selenium Chrome", file=sys.stderr)

        # Fallback: webdriver-manager + selenium Chrome
        try:
            service = ChromeService(ChromeDriverManager().install())
            return webdriver.Chrome(service=service, options=opts)
        except Exception:
            # Try default webdriver.Chrome(options=opts) as last resort
            return webdriver.Chrome(options=opts)

    elif browser.lower() == "firefox":
        opts = FOptions()
        if headless:
            opts.headless = True
        opts.set_preference("general.useragent.override", ua)
        service = FirefoxService(GeckoDriverManager().install())
        return webdriver.Firefox(service=service, options=opts)
    elif browser.lower() == "edge":
        opts = EOptions()
        if headless:
            opts.add_argument("--headless")
            opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1280,800")
        opts.add_argument(f"--user-agent={ua}")
        service = EdgeService(EdgeChromiumDriverManager().install())
        return webdriver.Edge(service=service, options=opts)
    raise ValueError("Unsupported browser")

# new helper: read existing success/failed files into sets
def load_existing_results():
    succ = set()
    fail = set()
    try:
        if os.path.exists(SUCCESS_FILE):
            with open(SUCCESS_FILE, encoding="utf-8") as f:
                succ = {ln.strip() for ln in f if ln.strip()}
        if os.path.exists(FAILED_FILE):
            with open(FAILED_FILE, encoding="utf-8") as f:
                fail = {ln.strip() for ln in f if ln.strip()}
    except Exception:
        pass
    return succ, fail

class NewsletterWorker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(str)
    success_url = pyqtSignal(str)
    failed_url = pyqtSignal(str)
    captcha_required = pyqtSignal()
    captcha_solved = pyqtSignal()
    email_processed = pyqtSignal(str, bool)   # email, had_success

    def __init__(self, emails, per_email_limit, browser, headless, append_results=True, rotate_files=False):
        super().__init__()
        self.emails = emails
        # per-email limit: how many successful signups to collect for one input email
        self.per_email_limit = per_email_limit
        self.browser = browser
        self.headless = headless
        self.append_results = append_results
        self.rotate_files = rotate_files
        self._abort = False
        self.cookies_path = COOKIES_FILE
        self.driver = None                # <-- keep driver reference for abort/interrupt
        # automatically close browsers created by this worker when the worker finishes
        self.auto_close_on_finish = True
        # verification settings (set by MainWindow.start)
        self.verify_enabled = False
        self.verify_clicks = 0
        # whether to perform newsletter signup (subscribe). When False worker will only attempt confirmations.
        self.perform_signup = True

    def abort(self):
        """Signal abort; try to interrupt any in-progress page loads so the worker can stop faster.
        This does not quit the browser (user requested browsers remain open)."""
        self._abort = True
        try:
            if self.driver:
                # attempt to stop any current page load (safe best-effort)
                try:
                    self.driver.execute_script("window.stop();")
                except Exception:
                    pass
        except Exception:
            pass

    def close_browser(self):
        """Best-effort close/quit the browser used by this worker.
        Only close drivers that were created/marked by this script."""
        try:
            drv = self.driver
            if not drv:
                return
            # only close drivers we created
            if not getattr(drv, "_copilot_managed", False):
                # don't close external browser instances
                return
            try:
                drv.execute_script("window.close();")
            except Exception:
                pass
            try:
                drv.quit()
            except Exception:
                pass
        except Exception:
            pass
        finally:
            self.driver = None

    def run(self):
        driver = None
        try:
            driver = build_driver(self.browser, self.headless)
            # mark driver as managed so we only close script-created browsers
            try:
                setattr(driver, "_copilot_managed", True)
            except Exception:
                pass
            # keep driver reference on the worker so abort() can interrupt
            self.driver = driver
            driver.set_page_load_timeout(20)
            self._prepare_result_files()
            for email in self.emails:
                if self._abort:
                    break
                self.progress.emit(f"[{timestamp()}] 🔁 Using email: {email}")
                ok_count = self._process_email(driver, email)
                # emit per-email processed and persist to processed file
                had_success = ok_count > 0
                try:
                    with PROCESS_LOCK:
                        with open(PROCESSED_FILE, "a", encoding="utf-8") as pf:
                            pf.write(email + "\n")
                except Exception as e:
                    self.progress.emit(f"[{timestamp()}] ⚠️ Could not write to {PROCESSED_FILE}: {e}")
                self.email_processed.emit(email, had_success)
        except Exception as e:
            self.progress.emit(f"[{timestamp()}] ❌ Fatal: {e}")
        finally:
            # By default close the browser we created when this worker finishes (only managed ones).
            try:
                if getattr(self, "auto_close_on_finish", True):
                    try:
                        self.close_browser()
                    except Exception:
                        # best-effort: fallback to direct quit if possible
                        try:
                            if driver:
                                driver.quit()
                        except Exception:
                            pass
                else:
                    # leave reference for stop() to close later
                    self.driver = driver
            except Exception:
                # ensure we don't hold a stale reference
                try:
                    self.driver = None
                except Exception:
                    pass
            self.finished.emit()

    def _prepare_result_files(self):
        if self.rotate_files:
            ts = time.strftime("%Y%m%d-%H%M%S")
            for f in (SUCCESS_FILE, FAILED_FILE):
                if os.path.exists(f) and os.path.getsize(f) > 0:
                    backup = f"{f.rsplit('.', 1)[0]}_{ts}.txt"
                    try:
                        Path(f).rename(backup)
                        self.progress.emit(f"[{timestamp()}] 📦 Rotated {f} -> {backup}")
                    except Exception as e:
                        self.progress.emit(f"[{timestamp()}] ⚠️ Could not rotate {f}: {e}")

        for f in (SUCCESS_FILE, FAILED_FILE):
            if not os.path.exists(f):
                Path(f).write_text("", encoding="utf-8")
            else:
                if not self.append_results:
                    try:
                        Path(f).write_text("", encoding="utf-8")
                        self.progress.emit(f"[{timestamp()}] ♻️ Cleared {f}")
                    except Exception as e:
                        self.progress.emit(f"[{timestamp()}] ⚠️ Could not clear {f}: {e}")

    def is_captcha_present(self, driver) -> bool:
        try:
            driver.switch_to.default_content()
            for iframe in driver.find_elements(By.TAG_NAME, 'iframe'):
                try:
                    src = iframe.get_attribute('src') or ''
                    if 'recaptcha' in src.lower():
                        return True
                except StaleElementReferenceException:
                    continue
            page = driver.page_source.lower() if driver.page_source else ""
            if "unusual traffic" in page:
                return True
            title = (driver.title or "").lower()
            if "not a robot" in title:
                return True
            return False
        except Exception:
            return False

    def save_google_cookies(self, driver):
        try:
            cookies = driver.get_cookies()
            with open(self.cookies_path, 'w', encoding='utf-8') as file:
                json.dump(cookies, file)
            self.progress.emit(f"[{timestamp()}] ✅ Google cookies saved")
        except Exception as e:
            self.progress.emit(f"[{timestamp()}] ⚠️ Failed to save cookies: {e}")

    def load_google_cookies(self, driver):
        if not os.path.exists(self.cookies_path):
            return False
        try:
            with open(self.cookies_path, 'r', encoding='utf-8') as file:
                cookies = json.load(file)
            driver.get("https://www.google.com/")
            time.sleep(1)
            for cookie in cookies:
                try:
                    driver.add_cookie(cookie)
                except Exception:
                    pass
            driver.refresh()
            time.sleep(1.5)
            self.progress.emit(f"[{timestamp()}] 🍪 Loaded saved Google cookies")
            return True
        except Exception as e:
            self.progress.emit(f"[{timestamp()}] ⚠️ Failed to load cookies: {e}")
            return False

    def _process_email(self, driver, email: str) -> int:
        # Two modes:
        # - perform_signup == True : search + subscribe flows (existing behavior)
        # - perform_signup == False: skip subscribe; only attempt email confirmations (verify_only)
        ok_count = 0
        main_window = None
        if getattr(self, "perform_signup", True):
            dork = random.choice(DORKS)
            links = self._search_links(driver, dork, pages=3, max_links=200)
            random.shuffle(links)
            main_window = driver.current_window_handle
            seen = getattr(self, "seen_links", set())
            for url in links:
                if url in seen:
                    self.progress.emit(f"[{timestamp()}] ↪️ Skipping already-seen link: {url}")
                    continue
                if self._abort or ok_count >= self.per_email_limit:
                    break
                res = self._subscribe(driver, url, email)
                if res == "success":
                    ok_count += 1
                    self.success_url.emit(url)
                    seen.add(url)
                    # optional confirmations after subscribe
                    if getattr(self, "verify_enabled", False) and self.verify_clicks > 0:
                        try:
                            creds = email.split(":", 1)
                            if len(creds) == 2 and creds[0] and creds[1]:
                                addr = creds[0].strip()
                                pwd = creds[1].strip()
                                self.progress.emit(f"[{timestamp()}] 🔁 Attempting confirmation checks for {addr}")
                                for i in range(self.verify_clicks):
                                    link = self._poll_for_confirmation(addr, pwd, timeout=90)
                                    if not link:
                                        self.progress.emit(f"[{timestamp()}] ⚠️ No confirmation email found for {addr} (attempt {i+1})")
                                        break
                                    try:
                                        driver.get(link)
                                        time.sleep(2.0)
                                        self.progress.emit(f"[{timestamp()}] ✅ Opened confirmation link for {addr}")
                                        # treat opened confirmation as another success (optional)
                                        self.success_url.emit(link)
                                    except Exception:
                                        break
                        except Exception:
                            pass
                else:
                    self.failed_url.emit(url)
                    seen.add(url)
                self.progress.emit(f"[{timestamp()}] {url} -> {res}")
                # Close any extra tabs opened by the page
                for handle in driver.window_handles:
                    if handle != main_window:
                        driver.switch_to.window(handle)
                        driver.close()
                driver.switch_to.window(main_window)
                time.sleep(random.uniform(0.8, 1.8))
            return ok_count
        else:
            # confirmation-only mode: try to poll IMAP for provided credentials and open confirmation links.
            successes = 0
            if getattr(self, "verify_enabled", False) and self.verify_clicks > 0:
                try:
                    creds = email.split(":", 1)
                    if len(creds) == 2 and creds[0] and creds[1]:
                        addr = creds[0].strip()
                        pwd = creds[1].strip()
                        self.progress.emit(f"[{timestamp()}] 🔁 Confirmation-only: checking inbox for {addr}")
                        for i in range(self.verify_clicks):
                            link = self._poll_for_confirmation(addr, pwd, timeout=90)
                            if not link:
                                self.progress.emit(f"[{timestamp()}] ⚠️ No confirmation email found for {addr} (attempt {i+1})")
                                break
                            try:
                                # open confirmation in a lightweight way (reuse/create driver)
                                try:
                                    driver.get(link)
                                    time.sleep(2.0)
                                except Exception:
                                    pass
                                self.progress.emit(f"[{timestamp()}] ✅ Opened confirmation link for {addr}")
                                self.success_url.emit(link)
                                successes += 1
                            except Exception:
                                break
                    else:
                        self.progress.emit(f"[{timestamp()}] ⚠️ No credentials provided for confirmation-only mode; skipping {email}")
                except Exception:
                    pass
            else:
                self.progress.emit(f"[{timestamp()}] ⚠️ Confirmation-only mode enabled but verification not configured; nothing to do for {email}")
            return successes

    # -------------------------------------------------
    def _google_links(self, driver, query: str, pages: int, max_links: int) -> list:
        """Get search results with CAPTCHA handling"""
        # Try cookie reuse to avoid CAPTCHA
        self.load_google_cookies(driver)

        # Open Google
        driver.get("https://www.google.com/")
        time.sleep(0.8)

        # Check for CAPTCHA
        if self.is_captcha_present(driver):
            self.progress.emit(f"[{timestamp()}] ⚠️ Google CAPTCHA detected! Please solve it.")
            self.captcha_required.emit()

            # Wait for user (2 minutes max)
            loop = QEventLoop()
            self.captcha_solved.connect(loop.quit)
            QTimer.singleShot(120000, loop.quit)
            loop.exec_()

            try:
                driver.refresh()
                time.sleep(1.5)
            except Exception as e:
                self.progress.emit(f"[{timestamp()}] ⚠️ Error refreshing page: {e}")
                return []

            if self.is_captcha_present(driver):
                self.progress.emit(f"[{timestamp()}] ❌ CAPTCHA still present.")
                return []
            else:
                self.progress.emit(f"[{timestamp()}] ✅ CAPTCHA resolved.")
                self.save_google_cookies(driver)

        # Perform search
        try:
            WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.NAME, "q"))).send_keys(query + Keys.RETURN)
            WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.ID, "search")))
        except TimeoutException:
            # Try once more after refresh (and maybe CAPTCHA)
            try:
                driver.refresh()
                time.sleep(1.2)
                if self.is_captcha_present(driver):
                    self.progress.emit(f"[{timestamp()}] ⚠️ CAPTCHA appeared after search attempt")
                    self.captcha_required.emit()

                    loop = QEventLoop()
                    self.captcha_solved.connect(loop.quit)
                    QTimer.singleShot(120000, loop.quit)
                    loop.exec_()

                    driver.refresh()
                    time.sleep(1.2)

                    if self.is_captcha_present(driver):
                        return []
                # Try search again
                driver.get("https://www.google.com/")
                time.sleep(0.8)
                WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.NAME, "q"))).send_keys(query + Keys.RETURN)
                WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.ID, "search")))
            except Exception:
                return []

        links = []
        for _ in range(pages):
            try:
                cards = driver.find_elements(By.CSS_SELECTOR, "div#search a h3")
            except StaleElementReferenceException:
                cards = driver.find_elements(By.CSS_SELECTOR, "div#search a h3")

            for h in cards:
                try:
                    a = h.find_element(By.XPATH, "./ancestor::a[1]")
                    href = (a.get_attribute("href") or "")
                    if "google.com/url?" in href:
                        href = parse_qs(urlsplit(href).query).get("q", [""])[0]

                    if href and href.startswith("http") and not is_blocked(href):
                        links.append(href)
                        if len(links) >= max_links:
                            break
                except Exception:
                    continue

            try:
                next_btn = driver.find_element(By.ID, "pnnext")
                next_btn.click()
                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "search")))
            except Exception:
                break

        # keep unique order
        return list(dict.fromkeys(links))

    # -------------------------------------------------
    def _search_links(self, driver, query: str, pages: int, max_links: int) -> list:
        """Try Google first; if results are few or none, fallback to Bing and DuckDuckGo."""
        links = []
        try:
            links = self._google_links(driver, query, pages=pages, max_links=max_links)
        except Exception:
            links = []

        # If Google produced few results or none, try Bing then DuckDuckGo
        if not links or len(links) < max(10, max_links // 6):
            try:
                bing = self._bing_links(driver, query, pages=pages, max_links=max_links)
                if bing:
                    return bing
            except Exception:
                pass
            try:
                ddg = self._duckduckgo_links(driver, query, pages=pages, max_links=max_links)
                if ddg:
                    return ddg
            except Exception:
                pass
        return links

    def _bing_links(self, driver, query: str, pages: int, max_links: int) -> list:
        links = []
        for p in range(pages):
            try:
                url = f"https://www.bing.com/search?q={quote_plus(query)}&first={p*10+1}"
                driver.get(url)
                time.sleep(0.8)
                if self.is_captcha_present(driver):
                    self.progress.emit(f"[{timestamp()}] ⚠️ Bing CAPTCHA detected; skipping Bing.")
                    break
                # common result selector for Bing
                items = driver.find_elements(By.CSS_SELECTOR, "li.b_algo h2 a")
                for a in items:
                    try:
                        href = (a.get_attribute("href") or "")
                        if href and href.startswith("http") and not is_blocked(href):
                            links.append(href)
                            if len(links) >= max_links:
                                return list(dict.fromkeys(links))
                    except Exception:
                        continue
            except Exception:
                continue
        return list(dict.fromkeys(links))

    def _duckduckgo_links(self, driver, query: str, pages: int, max_links: int) -> list:
        links = []
        for p in range(pages):
            try:
                # DuckDuckGo supports simple q param; offset handled poorly, so we just request same page repeatedly
                url = f"https://duckduckgo.com/?q={quote_plus(query)}&t=h_&ia=web"
                driver.get(url)
                time.sleep(0.8)
                if self.is_captcha_present(driver):
                    self.progress.emit(f"[{timestamp()}] ⚠️ DuckDuckGo CAPTCHA detected; skipping DuckDuckGo.")
                    break
                # result links are under a.result__a or a[data-testid='result-title-a']
                items = driver.find_elements(By.CSS_SELECTOR, "a.result__a, a[data-testid='result-title-a']")
                for a in items:
                    try:
                        href = (a.get_attribute("href") or "")
                        if href and href.startswith("http") and not is_blocked(href):
                            links.append(href)
                            if len(links) >= max_links:
                                return list(dict.fromkeys(links))
                    except Exception:
                        continue
            except Exception:
                continue
        return list(dict.fromkeys(links))

    # -------------------------------------------------
    def _subscribe(self, driver, url: str, email: str) -> str:
        try:
            driver.get(url)
            WebDriverWait(driver, 12).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            return "failed (load)"

        self._accept_cookies(driver)

        # Prepare data
        # If input line includes credentials like "user@example.com:appPassword",
        # use only the address to fill the newsletter form.
        info = random_info()
        try:
            addr = email.split(":", 1)[0].strip()
            if addr:
                info["email"] = addr
            else:
                info["email"] = email
        except Exception:
            info["email"] = email

        # Find form either in page or inside iframe; keep frame reference
        container, frame = self._find_form_or_iframe(driver)
        if not container:
            return "skipped (no form)"

        try:
            if frame is not None:
                driver.switch_to.frame(frame)

            self._fill_inputs(container, info)
            # pass driver so we can execute JS safely when needed
            self._tick_consents(container, driver)
            # also try to select any category/type checkboxes (some forms require selecting topics)
            self._select_all_checkboxes(container, driver)
            sub = self._find_submit(container)

            if sub:
                try:
                    sub.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", sub)

                # Wait for submission result
                try:
                    WebDriverWait(driver, 6).until(EC.staleness_of(sub))
                except Exception:
                    time.sleep(2.0)

                # Basic success heuristics
                page_src = ""
                try:
                    page_src = driver.page_source.lower()
                except Exception:
                    pass

                success_markers = [
                    "thank", "subscription confirmed", "check your email",
                    "successfully subscribed", "you're in", "thanks for subscribing",
                    "almost finished", "confirm your subscription"
                ]
                if any(x in page_src for x in success_markers):
                    return "success"

        except (ElementClickInterceptedException, StaleElementReferenceException, NoSuchElementException) as e:
            self.progress.emit(f"[{timestamp()}] Error: {e}")
            return "failed"
        except Exception as e:
            self.progress.emit(f"[{timestamp()}] Error: {e}")
        finally:
            # Always go back to default content if we switched
            try:
                driver.switch_to.default_content()
            except Exception:
                pass

        return "failed"

    # -------------------------------------------------
    def _accept_cookies(self, driver):
        try:
            # Try obvious consent buttons
            for sel in [
                "//button[contains(translate(., 'ACEJOPRTU\\'', 'acejoprtu’'), 'accept')]",
                "//button[contains(translate(., 'AGREE', 'agree'), 'agree')]",
                "//button[contains(translate(., 'OK', 'ok'), 'ok')]",
                "//button[contains(translate(., 'ACCEPTE', 'accepte'), 'accepte')]",
            ]:
                btns = driver.find_elements(By.XPATH, sel)
                for btn in btns:
                    try:
                        btn.click()
                        time.sleep(0.2)
                        return
                    except Exception:
                        pass
        except Exception:
            pass

        # fallback: brute search buttons/links
        try:
            for btn in driver.find_elements(By.XPATH, "//button | //a | //*[@role='button']"):
                txt = (btn.text or "").strip().lower()
                if any(k in txt for k in ["accept", "agree", "ok", "j'accepte", "tout accepter"]):
                    try:
                        btn.click()
                        time.sleep(0.2)
                        return
                    except Exception:
                        continue
        except Exception:
            pass

    def _find_form_or_iframe(self, driver):
        """Return (form_element, frame_element_or_None). If in iframe, return the iframe so caller can switch in."""
        # First try main document
        try:
            forms = driver.find_elements(By.TAG_NAME, "form")
            for f in forms:
                if f.find_elements(By.XPATH, ".//input[@type='email']"):
                    return f, None
        except Exception:
            pass

        # Then try common newsletter providers inside iframes
        providers = [
            "list-manage.com", "klaviyo.com", "hsforms.net", "hubspot.com",
            "activehosted.com", "convertkit.com", "ck.page", "aweber.com",
            "omnisend.com", "mailchimp", "sendinblue", "mailerlite"
        ]
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                src = (iframe.get_attribute("src") or "").lower()
                if any(p in src for p in providers):
                    try:
                        driver.switch_to.frame(iframe)
                        forms = driver.find_elements(By.TAG_NAME, "form")
                        for f in forms:
                            if f.find_elements(By.XPATH, ".//input[@type='email']"):
                                # IMPORTANT: return form + the iframe element so caller can switch into it again
                                driver.switch_to.default_content()
                                return f, iframe
                        driver.switch_to.default_content()
                    except Exception:
                        driver.switch_to.default_content()
        except Exception:
            pass

        return None, None

    def _fill_inputs(self, container, info: dict):
        inputs = []
        try:
            inputs = container.find_elements(By.XPATH, ".//input")
        except Exception:
            return

        for inp in inputs:
            try:
                itype = (inp.get_attribute("type") or "text").lower()
                name = (inp.get_attribute("name") or "").lower()
                placeholder = (inp.get_attribute("placeholder") or "").lower()
                aria_label = (inp.get_attribute("aria-label") or "").lower()
                label_text = ""
                hint = " ".join([name, placeholder, aria_label, label_text])

                val = ""
                if itype == "email":
                    val = info["email"]
                elif "name" in hint and "first" in hint:
                    val = info["first"]
                elif "name" in hint and "last" in hint:
                    val = info["last"]
                elif "name" in hint and ("full" in hint or hint.strip() == "name"):
                    val = info["name"]
                elif any(k in hint for k in ["phone", "tel"]):
                    val = info["phone"]
                elif any(k in hint for k in ["address", "street"]):
                    val = info["address"]
                elif "city" in hint:
                    val = info["city"]
                elif any(k in hint for k in ["state", "region", "province"]):
                    val = info["state"]
                elif any(k in hint for k in ["zip", "postal"]):
                    val = info["zip"]
                elif "country" in hint:
                    val = info["country"]
                elif any(k in hint for k in ["company", "organization"]):
                    val = info["company"]
                elif any(k in hint for k in ["birth", "dob"]):
                    val = info["birthday"]
                elif any(k in hint for k in ["job", "title"]):
                    val = info["job"]
                elif any(k in hint for k in ["website", "url"]):
                    val = info["website"]
                else:
                    continue

                try:
                    inp.clear()
                except Exception:
                    pass
                inp.send_keys(val)
            except Exception:
                continue

    def _tick_consents(self, container, driver):
        try:
            checks = container.find_elements(By.XPATH, ".//input[@type='checkbox']")
        except Exception:
            checks = []

        for chk in checks:
            try:
                label_text = ""
                try:
                    label = container.find_element(By.XPATH, f".//label[@for='{chk.get_attribute('id')}']")
                    label_text = (label.text or "").lower()
                except Exception:
                    try:
                        label_text = chk.find_element(By.XPATH, "./..").text.lower()
                    except Exception:
                        label_text = ""

                if any(k in label_text for k in [
                    "agree", "consent", "gdpr", "privacy", "terms", "policy",
                    "marketing", "j'accepte", "accepte", "autorise"
                ]):
                    if not chk.is_selected():
                        try:
                            chk.click()
                        except ElementClickInterceptedException:
                            # use the provided driver to perform a JS click if normal click is blocked
                            try:
                                driver.execute_script("arguments[0].click();", chk)
                            except Exception:
                                pass
            except Exception:
                continue

    def _find_submit(self, container):
        # direct submit elements
        for sel in [".//button[@type='submit']", ".//input[@type='submit']"]:
            try:
                el = container.find_element(By.XPATH, sel)
                if el:
                    return el
            except Exception:
                pass

        # textual buttons
        try:
            for btn in container.find_elements(By.XPATH, ".//button | .//a | .//input[@type='button']"):
                text = (btn.text or "").lower()
                value = (btn.get_attribute("value") or "").lower()
                candidate = text + " " + value
                if any(k in candidate for k in [
                    "subscribe", "sign up", "sign-up", "signup", "join", "get updates",
                    "get started", "submit", "go", "soumettre", "s'abonner", "m'inscrire",
                    "inscrivez-vous", "rejoindre", "recevoir", "s'inscrire", "register"
                ]):
                    return btn
        except Exception:
            pass

        return None

    # -------------------------------------------------
    def _select_all_checkboxes(self, container, driver):
        """Select all visible/enabled checkboxes inside the given container (safe click + JS fallback)."""
        try:
            checks = container.find_elements(By.XPATH, ".//input[@type='checkbox']")
        except Exception:
            checks = []

        for chk in checks:
            try:
                # skip already selected or not interactable
                try:
                    if chk.is_selected():
                        continue
                    if not chk.is_enabled():
                        continue
                    # many sites hide real checkboxes; ensure visible
                    if not chk.is_displayed():
                        # still attempt JS click for hidden-but-required checkboxes
                        try:
                            driver.execute_script("arguments[0].click();", chk)
                            continue
                        except Exception:
                            continue
                except Exception:
                    pass

                try:
                    chk.click()
                except ElementClickInterceptedException:
                    try:
                        # scroll into view then JS click
                        driver.execute_script("arguments[0].scrollIntoView(true);", chk)
                        driver.execute_script("arguments[0].click();", chk)
                    except Exception:
                        pass
                except Exception:
                    try:
                        driver.execute_script("arguments[0].click();", chk)
                    except Exception:
                        pass
            except Exception:
                continue

    # -------------------------------------------------
    def _extract_confirmation_link_from_text(self, txt: str):
        if not txt:
            return None
        urls = re.findall(r'https?://[^\s\'"<>]+', txt)
        for u in urls:
            if re.search(r'confirm|verify|subscription|activate|token', u, re.I):
                return u
        return urls[0] if urls else None

    def _guess_imap_host(self, addr: str) -> str:
        d = addr.split("@")[-1].lower()
        if "gmail" in d:
            return "imap.gmail.com"
        if "yahoo" in d:
            return "imap.mail.yahoo.com"
        if any(x in d for x in ("outlook", "hotmail", "live")):
            return "imap-mail.outlook.com"
        # fallback
        return f"imap.{d}"

    def _poll_for_confirmation(self, addr: str, pwd: str, timeout: int = 90):
        """Poll IMAP for messages and return a confirmation link only when the message
        looks like a confirmation for the target address (From or Subject contains keywords or the address)."""
        host = self._guess_imap_host(addr)
        end = time.time() + timeout
        keywords = re.compile(r'confirm|verify|subscription|activate|welcome|confirm your|double opt', re.I)

        def looks_like_confirmation(msg):
            subj = (msg.get('Subject') or "").lower()
            frm = (msg.get('From') or "").lower()
            to = (msg.get('To') or "").lower()
            # If subject or from contains confirmation keywords OR the target address appears in to/from/subject
            if keywords.search(subj) or keywords.search(frm):
                return True
            if addr.lower() in subj or addr.lower() in frm or addr.lower() in to:
                return True
            return False

        while time.time() < end and not self._abort:
            try:
                M = imaplib.IMAP4_SSL(host, timeout=10)
                M.login(addr, pwd)
                M.select("INBOX")

                # First check unseen messages but only accept those that match our heuristics
                typ, data = M.search(None, '(UNSEEN)')
                ids = data[0].split() if data and data[0] else []
                # check newest first
                for mid in reversed(ids):
                    try:
                        typ, msgdata = M.fetch(mid, '(RFC822)')
                        if not msgdata:
                            continue
                        raw = msgdata[0][1]
                        msg = email_pkg.message_from_bytes(raw)
                        if not looks_like_confirmation(msg):
                            # skip unrelated unseen emails
                            continue
                        # extract best payload and link
                        payload = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                ct = part.get_content_type()
                                if ct == "text/html":
                                    payload = part.get_payload(decode=True).decode(errors='ignore')
                                    break
                                if ct == "text/plain" and not payload:
                                    payload = part.get_payload(decode=True).decode(errors='ignore')
                        else:
                            payload = msg.get_payload(decode=True).decode(errors='ignore')
                        link = self._extract_confirmation_link_from_text(payload)
                        if link:
                            try:
                                M.store(mid, '+FLAGS', '\\Seen')
                            except Exception:
                                pass
                            try:
                                M.logout()
                            except Exception:
                                pass
                            return link
                    except Exception:
                        continue

                # If no suitable UNSEEN message, scan recent messages (limit to last 30) for a matching confirmation
                typ, data = M.search(None, 'ALL')
                ids = data[0].split() if data and data[0] else []
                if ids:
                    recent = ids[-30:]
                    for mid in reversed(recent):
                        try:
                            typ, msgdata = M.fetch(mid, '(RFC822)')
                            if not msgdata:
                                continue
                            raw = msgdata[0][1]
                            msg = email_pkg.message_from_bytes(raw)
                            if not looks_like_confirmation(msg):
                                continue
                            payload = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    ct = part.get_content_type()
                                    if ct == "text/html":
                                        payload = part.get_payload(decode=True).decode(errors='ignore')
                                        break
                                    if ct == "text/plain" and not payload:
                                        payload = part.get_payload(decode=True).decode(errors='ignore')
                            else:
                                payload = msg.get_payload(decode=True).decode(errors='ignore')
                            link = self._extract_confirmation_link_from_text(payload)
                            if link:
                                try:
                                    M.store(mid, '+FLAGS', '\\Seen')
                                except Exception:
                                    pass
                                try:
                                    M.logout()
                                except Exception:
                                    pass
                                return link
                        except Exception:
                            continue

                try:
                    M.logout()
                except Exception:
                    pass
            except Exception:
                # ignore transient IMAP errors and retry
                pass
            time.sleep(5)
        return None


# ---------------------------
#  Beautiful GUI
# ---------------------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎩  Newsletter Bot 3.0 (undetected)")
        self.resize(720, 660)
        self._apply_dark_fusion()
        self._build_ui()
        self.worker = None
        self.thread = None
        # multi-worker state
        self.threads = []
        self.workers = []
        self.active_workers = 0
        self.total_emails = 0
        self.processed_count = 0
        self.total_successes = 0
        self.email_source_path = None   # path of file loaded by user (if any)
        # in-memory result sets to avoid duplicates and seed progress
        self.existing_success = set()
        self.existing_failed = set()

    # ...existing UI and logic identical to v2.py...
    # For brevity the UI and other methods are the same as in your v2.py;
    # include the same implementations as in v2.py (load_emails, start, stop, logging, handlers, etc.)
    # ...existing code...
    def _apply_dark_fusion(self):
        QApplication.setStyle("Fusion")
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(37, 37, 38))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(30, 30, 30))
        palette.setColor(QPalette.AlternateBase, QColor(37, 37, 38))
        palette.setColor(QPalette.ToolTipBase, Qt.white)
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(45, 45, 48))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(90, 150, 250))
        palette.setColor(QPalette.Highlight, QColor(90, 150, 250))
        palette.setColor(QPalette.HighlightedText, Qt.black)
        QApplication.setPalette(palette)

        self.setStyleSheet("""
            QWidget { font-size: 11pt; }
            QGroupBox {
                border: 1px solid #4b4b4b; border-radius: 10px; margin-top: 12px; padding: 10px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
            QPushButton {
                padding: 8px 14px; border-radius: 10px; border: 1px solid #5a5a5a;
            }
            QPushButton:hover { border-color: #7aa2ff; }
            QPushButton:disabled { color: #9a9a9a; }
            QTextEdit {
                border: 1px solid #4b4b4b; border-radius: 8px; padding: 8px; font-family: Consolas, monospace;
            }
            QComboBox, QSpinBox, QProgressBar {
                border: 1px solid #4b4b4b; border-radius: 8px; padding: 4px 6px;
            }
            QProgressBar::chunk { background-color: #5a8cff; border-radius: 8px; }
        """)

    def _build_ui(self):
        # identical to v2.py UI construction (load emails, settings, buttons, progress, log)
        layout = QVBoxLayout(self)
        self.email_edit = QTextEdit()
        self.email_edit.setPlaceholderText("Paste e-mails (one per line) or load email.txt")
        layout.addWidget(QLabel("📧 E-mails:"))
        layout.addWidget(self.email_edit)

        h_counts = QHBoxLayout()
        self.loaded_label = QLabel("Loaded: 0")
        h_counts.addWidget(self.loaded_label)
        h_counts.addStretch(1)
        h_counts.addWidget(QLabel("Parallel browsers:"))
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 10)
        self.parallel_spin.setValue(1)
        h_counts.addWidget(self.parallel_spin)
        layout.addLayout(h_counts)

        gbox = QGroupBox("Settings")
        grid = QGridLayout(gbox)

        self.per_email_spin = QSpinBox()
        self.per_email_spin.setRange(1, 99)
        self.per_email_spin.setValue(3)

        self.total_success_spin = QSpinBox()
        self.total_success_spin.setRange(0, 9999)
        self.total_success_spin.setValue(0)

        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["Chrome", "Firefox", "Edge"])

        self.headless_check = QCheckBox("Hide browser (headless)")

        self.append_check = QCheckBox("Append to results (don’t clear files)")
        self.append_check.setChecked(True)
        self.rotate_check = QCheckBox("Rotate old results (timestamp backup)")
        self.rotate_check.setChecked(True)

        self.verify_check = QCheckBox("Enable email confirmation")
        self.verify_check.setChecked(False)
        self.verify_clicks_spin = QSpinBox()
        self.verify_clicks_spin.setRange(0, 100000)
        self.verify_clicks_spin.setValue(0)

        self.signup_check = QCheckBox("Subscribe to newsletters (perform signup)")
        self.signup_check.setChecked(True)

        grid.addWidget(QLabel("🎯 Per-email successes (how many successes to collect per input email):"), 0, 0)
        grid.addWidget(self.per_email_spin, 0, 1)
        grid.addWidget(QLabel("🏁 Total successes needed (0 = process all emails):"), 1, 0)
        grid.addWidget(self.total_success_spin, 1, 1)
        grid.addWidget(QLabel("🌐 Browser:"), 2, 0)
        grid.addWidget(self.browser_combo, 2, 1)
        grid.addWidget(self.headless_check, 3, 0, 1, 2)
        grid.addWidget(self.append_check, 4, 0, 1, 2)
        grid.addWidget(self.rotate_check, 5, 0, 1, 2)
        grid.addWidget(self.verify_check, 6, 0, 1, 2)
        grid.addWidget(QLabel("Confirmations per success:"), 7, 0)
        grid.addWidget(self.verify_clicks_spin, 7, 1)
        grid.addWidget(self.signup_check, 8, 0, 1, 2)
        layout.addWidget(gbox)

        h = QHBoxLayout()
        self.load_btn = QPushButton("📂 Load email.txt")
        self.load_btn.clicked.connect(self.load_emails)
        self.start_btn = QPushButton("▶️ Start")
        self.start_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton("⏹️ Stop")
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setEnabled(False)
        h.addWidget(self.load_btn)
        h.addWidget(self.start_btn)
        h.addWidget(self.stop_btn)
        layout.addLayout(h)

        self.pbar = QProgressBar()
        self.pbar.setTextVisible(True)
        layout.addWidget(self.pbar)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(QLabel("📄 Log:"))
        layout.addWidget(self.log_edit)

        # Footer: attribution + clickable Telegram link
        self.footer_label = QLabel('<small>by achraf48.co — <a href="https://t.me/ouchen2">telegram</a></small>')
        self.footer_label.setAlignment(Qt.AlignCenter)
        self.footer_label.setOpenExternalLinks(True)
        # muted color for footer
        self.footer_label.setStyleSheet("color: #9a9a9a; font-size: 9pt; margin-top:8px;")
        layout.addWidget(self.footer_label)

    # The rest of MainWindow methods (load_emails, start, stop, handlers, log, add_success, add_failed, captcha handling)
    # should be the same as in your v2.py — copy them here unchanged.
    # ...existing code...
    def load_emails(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select email.txt", "", "Text files (*.txt)")
        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    txt = f.read()
                    self.email_edit.setPlainText(txt)
                    emails = [e.strip() for e in txt.splitlines() if e.strip()]
                    self.total_emails = len(emails)
                    self.loaded_label.setText(f"Loaded: {self.total_emails}")
                    self.email_source_path = path
            except Exception as e:
                QMessageBox.critical(self, "Load error", f"Could not read file:\n{e}")

    def start(self):
        emails = [e.strip() for e in self.email_edit.toPlainText().splitlines() if e.strip()]
        if not emails:
            QMessageBox.warning(self, "Error", "No e-mails provided.")
            return

        # UI: indicate run state immediately (disable inputs, enable Stop)
        try:
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.load_btn.setEnabled(False)
            self.browser_combo.setEnabled(False)
            self.headless_check.setEnabled(False)
            self.append_check.setEnabled(False)
            self.rotate_check.setEnabled(False)
            self.per_email_spin.setEnabled(False)
            self.total_success_spin.setEnabled(False)
            self.parallel_spin.setEnabled(False)
            # optional: lock confirmation/signup options while running
            try:
                self.verify_check.setEnabled(False)
                self.verify_clicks_spin.setEnabled(False)
                self.signup_check.setEnabled(False)
            except Exception:
                pass
        except Exception:
            pass

        # load existing results before workers rotate/modify files
        succ_set, fail_set = load_existing_results()
        self.existing_success = succ_set
        self.existing_failed = fail_set

        per_email_limit = self.per_email_spin.value()
        total_wanted = self.total_success_spin.value()
        browser = self.browser_combo.currentText()
        headless = self.headless_check.isChecked()
        append_results = self.append_check.isChecked()
        rotate_files = self.rotate_check.isChecked()
        concurrency = self.parallel_spin.value()
        if concurrency > len(emails):
            concurrency = len(emails)

        # if user chose to clear files on start, drop in-memory seen sets
        if not append_results and not rotate_files:
            self.existing_success = set()
            self.existing_failed = set()

        # progress bar: seed starting successes with previously saved successes
        starting_successes = len(self.existing_success)
        if total_wanted == 0:
            self.pbar.setRange(0, len(emails))
            # if some successes already recorded, map processed count accordingly
            try:
                self.pbar.setValue(min(starting_successes, len(emails)))
            except Exception:
                pass
        else:
            self.pbar.setRange(0, total_wanted)
            try:
                self.pbar.setValue(min(starting_successes, total_wanted))
            except Exception:
                pass

        # create processed file if missing
        try:
            if not os.path.exists(PROCESSED_FILE):
                Path(PROCESSED_FILE).write_text("", encoding="utf-8")
        except Exception as e:
            self.log(f"[{timestamp()}] ⚠️ Could not create {PROCESSED_FILE}: {e}")

        chunks = [[] for _ in range(concurrency)]
        for i, e in enumerate(emails):
            chunks[i % concurrency].append(e)

        self.threads = []
        self.workers = []
        self.active_workers = 0

        for chunk in chunks:
            if not chunk:
                continue
            thread = QThread()
            worker = NewsletterWorker(chunk, per_email_limit, browser, headless,
                                      append_results=append_results,
                                      rotate_files=rotate_files)
            # set verification settings on worker (UI -> worker)
            try:
                worker.verify_enabled = bool(self.verify_check.isChecked())
                worker.verify_clicks = int(self.verify_clicks_spin.value())
                worker.perform_signup = bool(self.signup_check.isChecked())
            except Exception:
                worker.verify_enabled = False
                worker.verify_clicks = 0
                worker.perform_signup = True
            # give worker the seen-links so it can skip them early (includes previous successes & failures)
            worker.seen_links = set(self.existing_success) | set(self.existing_failed)

            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            worker.progress.connect(self.log)
            worker.success_url.connect(self.add_success)
            worker.failed_url.connect(self.add_failed)
            worker.email_processed.connect(self.handle_worker_email_processed)
            worker.finished.connect(self.handle_worker_finished)

            self.threads.append(thread)
            self.workers.append(worker)
            self.active_workers += 1
            thread.start()

    def stop(self):
        # request abort and force-close browsers for all workers
        for w in getattr(self, "workers", []):
            try:
                w.abort()
            except Exception:
                pass
        for w in getattr(self, "workers", []):
            try:
                w.close_browser()
            except Exception:
                pass
        # fallback single-worker
        try:
            if getattr(self, "worker", None):
                try:
                    self.worker.abort()
                    self.worker.close_browser()
                except Exception:
                    pass
        except Exception:
            pass
        self.log(f"[{timestamp()}] ⏹️ Requested stop and closed browsers.")
        # immediate UI restore so Stop isn't left enabled
        try:
            self.stop_btn.setEnabled(False)
            self.start_btn.setEnabled(True)
            self.load_btn.setEnabled(True)
            self.browser_combo.setEnabled(True)
            self.headless_check.setEnabled(True)
            self.append_check.setEnabled(True)
            self.rotate_check.setEnabled(True)
            self.per_email_spin.setEnabled(True)
            self.total_success_spin.setEnabled(True)
            self.parallel_spin.setEnabled(True)
            try:
                self.verify_check.setEnabled(True)
                self.verify_clicks_spin.setEnabled(True)
                self.signup_check.setEnabled(True)
            except Exception:
                pass
        except Exception:
            pass
        # ensure restore-on-finish logic can still run
        self.finished.connect(self._restore_ui_after_run)

    def handle_worker_email_processed(self, email, had_success):
        self.processed_count += 1
        self.loaded_label.setText(f"Processed: {self.processed_count} / {self.total_emails}")
        if self.total_success_spin.value() == 0:
            try:
                self.pbar.setValue(self.processed_count)
            except Exception:
                pass

        if self.email_source_path:
            try:
                with PROCESS_LOCK:
                    if os.path.exists(self.email_source_path):
                        with open(self.email_source_path, "r", encoding="utf-8") as sf:
                            lines = [ln.rstrip("\n") for ln in sf.readlines()]
                        new_lines = [ln for ln in lines if ln.strip() and ln.strip() != email]
                        if len(new_lines) != len(lines):
                            with open(self.email_source_path, "w", encoding="utf-8") as sf:
                                if new_lines:
                                    sf.write("\n".join(new_lines) + "\n")
                                else:
                                    sf.write("")
            except Exception as e:
                self.log(f"[{timestamp()}] ⚠️ Could not update source file: {e}")

        if had_success:
            self.total_successes += 1
            total_wanted = self.total_success_spin.value()
            if total_wanted > 0 and self.total_successes >= total_wanted:
                self.log(f"[{timestamp()}] ✅ Global success target reached ({self.total_successes}) — stopping all workers.")
                self.stop()

    def handle_worker_finished(self):
        self.active_workers -= 1
        if self.active_workers <= 0:
            self._restore_ui_after_run()

    def _restore_ui_after_run(self):
        # set progress to complete and restore UI controls
        try:
            self.pbar.setValue(self.pbar.maximum())
        except Exception:
            pass
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.load_btn.setEnabled(True)
        self.browser_combo.setEnabled(True)
        self.headless_check.setEnabled(True)
        self.append_check.setEnabled(True)
        self.rotate_check.setEnabled(True)
        self.per_email_spin.setEnabled(True)
        self.total_success_spin.setEnabled(True)
        self.parallel_spin.setEnabled(True)

    def log(self, txt):
        self.log_edit.append(txt)
        QApplication.processEvents()

    def add_success(self, url):
        # avoid writing duplicates by checking in-memory set
        try:
            if url in self.existing_success:
                return
            with PROCESS_LOCK:
                with open(SUCCESS_FILE, "a", encoding="utf-8") as f:
                    f.write(url + "\n")
                self.existing_success.add(url)
        except Exception as e:
            self.log(f"[{timestamp()}] ⚠️ Could not write to {SUCCESS_FILE}: {e}")
        try:
            self.pbar.setValue(self.pbar.value() + 1)
        except Exception:
            pass

    def add_failed(self, url):
        try:
            if url in self.existing_failed:
                return
            with PROCESS_LOCK:
                with open(FAILED_FILE, "a", encoding="utf-8") as f:
                    f.write(url + "\n")
                self.existing_failed.add(url)
        except Exception as e:
            self.log(f"[{timestamp()}] ⚠️ Could not write to {FAILED_FILE}: {e}")

    def handle_captcha_prompt(self):
        self.log(f"[{timestamp()}] 🛑 CAPTCHA detected! Please solve it in the browser window.")
        old_style = self.styleSheet()
        self.setStyleSheet(old_style + """
            QWidget { border: 2px solid #ff6b6b; }
            QTextEdit, QSpinBox, QComboBox { border: 1px solid #ff6b6b; }
        """)
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Google CAPTCHA Required")
        msg.setText("Google detected automated traffic and requires CAPTCHA verification.")
        msg.setInformativeText("Solve CAPTCHA in the browser window, then click OK to continue.")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Ok)
        result = msg.exec_()
        self.setStyleSheet(old_style)
        if result == QMessageBox.Ok:
            self.log(f"[{timestamp()}] ✅ User confirmed CAPTCHA resolved")
            # broadcast to all workers
            for w in getattr(self, "workers", []):
                try:
                    w.captcha_solved.emit()
                except Exception:
                    pass
            # fallback single-worker
            try:
                if getattr(self, "worker", None):
                    self.worker.captcha_solved.emit()
            except Exception:
                pass
        else:
            self.log(f"[{timestamp()}] 🛑 User canceled CAPTCHA resolution")
            self.stop()

    def on_captcha_resolved(self):
        self.log(f"[{timestamp()}] 🔄 Verifying CAPTCHA resolution…")
# ---------------------------
#  Entry
# ---------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
