import os
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from laptop import Laptop

BASE_URL = 'https://webscraper.io/'


class PageCache:
    # Keeps downloaded pages on disk, so running the script again (e.g. after changing
    # the report) doesn't download everything again.

    def __init__(self, folder='cache', max_age=timedelta(hours=24)):
        self.folder = Path(folder)
        self.max_age = max_age

    def __len__(self):
        return len(list(self.folder.glob('*.html'))) if self.folder.exists() else 0

    def __contains__(self, url):
        return self.get(url) is not None

    def _path(self, url):
        # https://webscraper.io/.../laptops?page=2 -> webscraper_io_..._laptops_page_2.html
        name = re.sub(r'^https?://', '', url)
        return self.folder / (re.sub(r'\W+', '_', name).strip('_') + '.html')

    def get(self, url):
        path = self._path(url)
        if not path.exists():
            return None
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        if age > self.max_age:
            return None
        with open(path, encoding='utf-8') as f:
            return f.read()

    def save(self, url, html):
        self.folder.mkdir(exist_ok=True)
        with open(self._path(url), 'w', encoding='utf-8') as f:
            f.write(html)

    def clear(self):
        removed = 0
        for path in self.folder.glob('*.html'):
            os.remove(path)
            removed += 1
        return removed


class Paginator:
    # for url, soup in Paginator(scraper, first_url): ...
    # keeps following the "next" link until there isn't one

    def __init__(self, scraper, start_url):
        self.scraper = scraper
        self.next_url = start_url
        self.page = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.next_url is None:
            raise StopIteration

        url = self.next_url
        soup = BeautifulSoup(self.scraper.get_html(url), 'html.parser')
        link = soup.select_one('a[rel=next]')
        self.next_url = urljoin(url, link['href']) if link else None
        self.page += 1
        return url, soup


class BaseScraper(ABC):
    user_agent = (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/130.0 Safari/537.36'
    )

    def __init__(self, base_url=BASE_URL, delay=0.5, cache=None):
        self.base_url = base_url
        self.delay = delay
        self.cache = cache
        self.downloaded = 0
        self.from_cache = 0
        self._session = requests.Session()
        self._session.headers['User-Agent'] = self.user_agent

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._session.close()

    @property
    def delay(self):
        return self.__delay

    @delay.setter
    def delay(self, seconds):
        if seconds < 0:
            raise ValueError("delay can't be negative")
        self.__delay = seconds

    @property
    @abstractmethod
    def start_url(self):
        ...

    @abstractmethod
    def parse_page(self, soup, url):
        ...

    def get_html(self, url, retries=3):
        # "is not None" on purpose: an empty cache has len() 0, which would count as False
        if self.cache is not None and (html := self.cache.get(url)) is not None:
            self.from_cache += 1
            return html

        for attempt in range(retries):
            try:
                r = self._session.get(url, timeout=20)
                r.raise_for_status()
                break
            except requests.RequestException as e:
                if attempt == retries - 1:
                    raise
                print(f'  {e}, retrying...')
                time.sleep(2)

        r.encoding = 'utf-8'
        self.downloaded += 1
        time.sleep(self.delay)
        if self.cache is not None:
            self.cache.save(url, r.text)
        return r.text

    def scrape(self):
        pages = Paginator(self, self.start_url)
        for url, soup in pages:
            items = self.parse_page(soup, url)
            print(f'Page {pages.page}: {len(items)} items')
            yield from items


class LaptopScraper(BaseScraper):
    path = 'test-sites/e-commerce/static/computers/laptops'

    @property
    def start_url(self):
        return urljoin(self.base_url, self.path)

    def parse_page(self, soup, url):
        return [Laptop.from_card(card, url) for card in soup.select('div.thumbnail')]
