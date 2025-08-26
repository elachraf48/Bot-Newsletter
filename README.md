# Newsletter Bot (v3)

A GUI tool to find newsletter signup forms on the web and attempt automated signups using provided e‑mail addresses. Features:
- Multi-engine discovery (Google primary, Bing and DuckDuckGo fallbacks).
- Heuristics to locate newsletter forms (including iframe providers).
- Per-email success limits and global success target.
- Options to append or rotate results files and avoid duplicate entries.
- Cookie reuse for Google to reduce CAPTCHAs.
- Workers run browser instances; only browsers created by the script are closed by stop.

## Prerequisites
- Python 3.8+
- Chrome/Firefox/Edge browser (for automated browsing)
- Recommended packages (install via pip):
  - PyQt5
  - selenium
  - webdriver-manager
  - faker
  - undetected-chromedriver (optional, improves Chrome stealth)

Example:
```
pip install PyQt5 selenium webdriver-manager faker undetected-chromedriver
```

## Files produced / used
- `success.txt` — unique URLs where signups were detected (duplicates avoided).
- `failed.txt` — URLs that failed (deduplicated).
- `processed_emails.txt` — e-mails that have been processed.
- `skip_domains.txt` — optional list of domain substrings to skip.
- `google_cookies.json` — saved Google cookies to help avoid CAPTCHAs.

## Running
- Launch the GUI by running the script:
  - `Bot Newsletter-v3.py` (standard)
  - `Bot Newsletter-v3(undetected).py` (tries undetected_chromedriver for Chrome when available)
- Paste or load a text file with one e-mail per line.
- Configure:
  - Parallel browsers: number of concurrent workers (threads).
  - Per-email successes: how many successful signups to collect before moving on from one input e-mail.
  - Total successes needed: global stop condition (0 = process all).
  - Browser: Chrome/Firefox/Edge.
  - Headless: run browsers hidden (may increase CAPTCHA likelihood).
  - Append to results: when checked, existing result files are preserved and duplicates are skipped.
  - Rotate old results: when checked, existing success/failed files are renamed with a timestamp before starting.

## Behavior & tips
- The app preloads existing success/failed entries and avoids reprocessing those URLs (so `Append to results` + "no duplicates" are supported).
- If `Rotate old results` is enabled, old files are backed up once on start; rotating will help you keep fresh logs while preserving previous runs.
- CAPTCHA handling:
  - Google is used first. When a CAPTCHA is detected the app will prompt you to solve it in the browser; cookies are saved after a successful manual resolution to reduce future prompts.
- Stopping:
  - "Stop" requests an abort and only closes browser instances created by the script (it will not close unrelated browser windows on your system).

## Troubleshooting
- Driver/binary errors: ensure a compatible browser and that chromedriver/geckodriver/msedgedriver can be installed (webdriver-manager handles this automatically if network access is available).
- Frequent CAPTCHAs: try running fewer parallel browsers, disable headless mode, or solve one CAPTCHA manually to save cookies.
- No results from Google: the app falls back to Bing and DuckDuckGo automatically.
- Duplicate links still appear: ensure `Append to results` is checked and that the `success.txt`/`failed.txt` files are not manually modified in a conflicting way while running.

## Safety and ethics
- Use this tool only with permission and for lawful purposes. Automated signups may violate some websites' terms of service.
- Respect rate limits and privacy regulations (GDPR etc.) when processing personal data.

## Contributing
- Improvements welcome: better form detection, provider-specific flows, and more robust CAPTCHA handling.
- Keep changes under the project root: `Documents\GitHub\newsletter`.

## License
- No license specified. Add a LICENSE file if you want to set terms for reuse.

