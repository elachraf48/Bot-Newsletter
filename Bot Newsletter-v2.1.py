import os
import sys
import time
import random
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlsplit

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

# webdriver-manager services
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager

from faker import Faker
fake = Faker()

# ---------- CONFIG ----------
DORKS = [
    'intitle:newsletter (subscribe OR "sign up")',
    'inurl:newsletter (subscribe OR signup)',
    '"subscribe to our newsletter" -site:facebook.com -site:twitter.com',
    '"join our newsletter" (footer OR subscribe)',
    '"get updates" (newsletter OR email) -site:facebook.com -site:twitter.com',
]

BLOCKED_DOMAINS_FILE = "skip_domains.txt"
SUCCESS_FILE = "success.txt"
FAILED_FILE = "failed.txt"
COOKIES_FILE = "google_cookies.json"
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
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36")
    if browser.lower() == "chrome":
        opts = COptions()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1280,800")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument(f"--user-agent={ua}")
        return webdriver.Chrome(options=opts)
    elif browser.lower() == "firefox":
        opts = FOptions()
        if headless:
            opts.add_argument("--headless")
        opts.set_preference("general.useragent.override", ua)
        return webdriver.Firefox(options=opts)
    elif browser.lower() == "edge":
        opts = EOptions()
        if headless:
            opts.add_argument("--headless")
        opts.add_argument("--window-size=1280,800")
        opts.add_argument(f"--user-agent={ua}")
        return webdriver.Edge(options=opts)
    raise ValueError("Unsupported browser")

class NewsletterWorker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(str)
    success_url = pyqtSignal(str)
    failed_url = pyqtSignal(str)
    captcha_required = pyqtSignal()
    captcha_solved = pyqtSignal()

    def __init__(self, emails, wanted, browser, headless, append_results=True, rotate_files=False):
        super().__init__()
        self.emails = emails
        self.wanted = wanted
        self.browser = browser
        self.headless = headless
        self.append_results = append_results
        self.rotate_files = rotate_files
        self._abort = False
        self.cookies_path = COOKIES_FILE

    def abort(self):
        self._abort = True

    def run(self):
        driver = None
        try:
            driver = build_driver(self.browser, self.headless)
            driver.set_page_load_timeout(20)
            self._prepare_result_files()
            success = 0
            for email in self.emails:
                if self._abort:
                    break
                self.progress.emit(f"[{timestamp()}] 🔁 Using email: {email}")
                ok = self._process_email(driver, email)
                success += ok
                if success >= self.wanted:
                    self.progress.emit(f"[{timestamp()}] ✅ Reached {self.wanted} successes – stopping.")
                    break
        except Exception as e:
            self.progress.emit(f"[{timestamp()}] ❌ Fatal: {e}")
        finally:
            # Leave browser open (no driver.quit())
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
        dork = random.choice(DORKS)
        links = self._google_links(driver, dork, pages=3, max_links=200)
        random.shuffle(links)
        ok_count = 0
        main_window = driver.current_window_handle

        for url in links:
            if self._abort or ok_count >= self.wanted:
                break
            res = self._subscribe(driver, url, email)
            if res == "success":
                ok_count += 1
                self.success_url.emit(url)
            else:
                self.failed_url.emit(url)
            self.progress.emit(f"[{timestamp()}] {url} -> {res}")
            # Close any extra tabs opened by the page
            for handle in driver.window_handles:
                if handle != main_window:
                    driver.switch_to.window(handle)
                    driver.close()
            driver.switch_to.window(main_window)
            time.sleep(random.uniform(0.8, 1.8))
        return ok_count

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
        info = random_info()
        info["email"] = email

        # Find form either in page or inside iframe; keep frame reference
        container, frame = self._find_form_or_iframe(driver)
        if not container:
            return "skipped (no form)"

        try:
            if frame is not None:
                driver.switch_to.frame(frame)

            self._fill_inputs(container, info)
            self._tick_consents(container)
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
                "//button[contains(translate(., 'ACEJOPRTU\'', 'acejoprtu’'), 'accept')]",
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

    def _tick_consents(self, container):
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
                            container._parent.execute_script("arguments[0].click();", chk)
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


# ---------------------------
#  Beautiful GUI
# ---------------------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎩  Newsletter Bot 2.1")
        self.resize(720, 620)
        self._apply_dark_fusion()
        self._build_ui()
        self.worker = None
        self.thread = None

    # -------------------------------------------------
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

        # subtle rounded controls
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

    # -------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        # e-mail area
        self.email_edit = QTextEdit()
        self.email_edit.setPlaceholderText("Paste e-mails (one per line) or load email.txt")
        layout.addWidget(QLabel("📧 E-mails:"))
        layout.addWidget(self.email_edit)

        # controls
        gbox = QGroupBox("Settings")
        grid = QGridLayout(gbox)

        self.success_spin = QSpinBox()
        self.success_spin.setRange(1, 9999)
        self.success_spin.setValue(10)

        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["Chrome", "Firefox", "Edge"])

        self.headless_check = QCheckBox("Hide browser (headless)")

        # NEW: result file behavior
        self.append_check = QCheckBox("Append to results (don’t clear files)")
        self.append_check.setChecked(True)  # Fixes your “empty file every start”
        self.rotate_check = QCheckBox("Rotate old results (timestamp backup)")

        grid.addWidget(QLabel("🎯 Successes needed:"), 0, 0)
        grid.addWidget(self.success_spin, 0, 1)
        grid.addWidget(QLabel("🌐 Browser:"), 1, 0)
        grid.addWidget(self.browser_combo, 1, 1)
        grid.addWidget(self.headless_check, 2, 0, 1, 2)
        grid.addWidget(self.append_check, 3, 0, 1, 2)
        grid.addWidget(self.rotate_check, 4, 0, 1, 2)
        layout.addWidget(gbox)

        # buttons
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

        # progress
        self.pbar = QProgressBar()
        self.pbar.setTextVisible(True)
        layout.addWidget(self.pbar)

        # log
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(QLabel("📄 Log:"))
        layout.addWidget(self.log_edit)

    # -------------------------------------------------
    def load_emails(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select email.txt", "", "Text files (*.txt)")
        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    self.email_edit.setPlainText(f.read())
            except Exception as e:
                QMessageBox.critical(self, "Load error", f"Could not read file:\n{e}")

    def start(self):
        emails = [e.strip() for e in self.email_edit.toPlainText().splitlines() if e.strip()]
        if not emails:
            QMessageBox.warning(self, "Error", "No e-mails provided.")
            return

        wanted = self.success_spin.value()
        browser = self.browser_combo.currentText()
        headless = self.headless_check.isChecked()
        append_results = self.append_check.isChecked()
        rotate_files = self.rotate_check.isChecked()

        # Setup thread & worker
        self.thread = QThread()
        self.worker = NewsletterWorker(
            emails, wanted, browser, headless,
            append_results=append_results,
            rotate_files=rotate_files
        )
        self.worker.moveToThread(self.thread)

        # signals
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.progress.connect(self.log)
        self.worker.success_url.connect(self.add_success)
        self.worker.failed_url.connect(self.add_failed)

        # CAPTCHA signals
        self.worker.captcha_required.connect(self.handle_captcha_prompt)
        self.worker.captcha_solved.connect(self.on_captcha_resolved)

        # UI state
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.load_btn.setEnabled(False)
        self.browser_combo.setEnabled(False)
        self.headless_check.setEnabled(False)
        self.append_check.setEnabled(False)
        self.rotate_check.setEnabled(False)
        self.success_spin.setEnabled(False)

        self.pbar.setRange(0, wanted)
        self.pbar.setValue(0)

        self.thread.start()

        # when thread finishes, restore UI
        self.thread.finished.connect(self._restore_ui_after_run)

    def _restore_ui_after_run(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.load_btn.setEnabled(True)
        self.browser_combo.setEnabled(True)
        self.headless_check.setEnabled(True)
        self.append_check.setEnabled(True)
        self.rotate_check.setEnabled(True)
        self.success_spin.setEnabled(True)

    def stop(self):
        if self.worker:
            self.worker.abort()
            self.log(f"[{timestamp()}] ⏹️ Requested stop…")

    def log(self, txt):
        self.log_edit.append(txt)
        QApplication.processEvents()

    def add_success(self, url):
        try:
            with open(SUCCESS_FILE, "a", encoding="utf-8") as f:
                f.write(url + "\n")
        except Exception as e:
            self.log(f"[{timestamp()}] ⚠️ Could not write to {SUCCESS_FILE}: {e}")
        self.pbar.setValue(self.pbar.value() + 1)

    def add_failed(self, url):
        try:
            with open(FAILED_FILE, "a", encoding="utf-8") as f:
                f.write(url + "\n")
        except Exception as e:
            self.log(f"[{timestamp()}] ⚠️ Could not write to {FAILED_FILE}: {e}")

    def handle_captcha_prompt(self):
        """Show CAPTCHA prompt to user and wait for resolution"""
        self.log(f"[{timestamp()}] 🛑 CAPTCHA detected! Please solve it in the browser window.")

        # visual cue
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
        self.setStyleSheet(old_style)  # reset

        if result == QMessageBox.Ok:
            self.log(f"[{timestamp()}] ✅ User confirmed CAPTCHA resolved")
            self.worker.captcha_solved.emit()
        else:
            self.log(f"[{timestamp()}] 🛑 User canceled CAPTCHA resolution")
            self.stop()

    def on_captcha_resolved(self):
        """Called when CAPTCHA is confirmed as resolved"""
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