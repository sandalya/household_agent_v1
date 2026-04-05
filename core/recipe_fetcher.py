"""Завантаження рецептів по URL."""
import logging
import re
import urllib.request
import urllib.error
from html.parser import HTMLParser

log = logging.getLogger("core.recipe_fetcher")

class _TextExtractor(HTMLParser):
    """Простий HTML → текст без зовнішніх залежностей."""
    SKIP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "iframe"}

    def __init__(self):
        super().__init__()
        self.result = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip == 0:
            text = data.strip()
            if text:
                self.result.append(text)

    def get_text(self):
        return "\n".join(self.result)


def fetch_recipe_text(url: str, max_chars: int = 8000) -> str:
    """Завантажує URL і повертає чистий текст (до max_chars символів)."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; HouseholdAgent/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            # визначаємо кодування
            charset = "utf-8"
            ct = resp.headers.get("Content-Type", "")
            m = re.search(r"charset=([^\s;]+)", ct)
            if m:
                charset = m.group(1)
            html = raw.decode(charset, errors="replace")

        parser = _TextExtractor()
        parser.feed(html)
        text = parser.get_text()

        # прибираємо зайві пробіли
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text[:max_chars]
        log.info(f"Завантажено {len(text)} символів з {url}")
        return text

    except urllib.error.URLError as e:
        log.error(f"Не вдалось завантажити {url}: {e}")
        return ""
    except Exception as e:
        log.error(f"Помилка fetch {url}: {e}")
        return ""


def extract_urls(text: str) -> list[str]:
    """Витягує всі URL з тексту."""
    pattern = r'https?://[^\s<>"\'()]+'
    return re.findall(pattern, text)
