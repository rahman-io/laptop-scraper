# Runs the scraper against a local copy of the test shop: the 117 real laptops
# (tests/products.txt + tests/descriptions.txt), 6 per page like on the site.

import html
import http.server
import os
import subprocess
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest
from openpyxl import load_workbook

ROOT = Path(__file__).parent.parent
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from catalog import Catalog
from scraper import BaseScraper, LaptopScraper, PageCache, Paginator

LIST_PATH = '/test-sites/e-commerce/static/computers/laptops'

CARD = '''<div class="col-md-4"><div class="card thumbnail"><div class="product-wrapper card-body">
<div class="caption"><h4 class="price float-end card-title pull-right"><span itemprop="price">{price}</span></h4>
<h4><a href="/test-sites/e-commerce/static/product/{id}" class="title" title="{title}">{short}</a></h4>
<p class="description card-text">{description}</p></div>
<div class="ratings"><p class="review-count float-end"><span itemprop="reviewCount">{reviews}</span> reviews</p>
<p data-rating="{rating}"></p></div></div></div></div>'''


def build_site():
    products = (HERE / 'products.txt').read_text(encoding='utf-8').splitlines()
    descriptions = (HERE / 'descriptions.txt').read_text(encoding='utf-8').splitlines()
    cards = []
    for line, description in zip(products, descriptions):
        id, title, price, rating, reviews = line.split('|')
        short = title if len(title) < 25 else title[:22] + '...'
        cards.append(CARD.format(id=id, title=html.escape(title), short=html.escape(short), price=price,
                                 description=html.escape(description), rating=rating, reviews=reviews))

    pages = {}
    chunks = [cards[i:i + 6] for i in range(0, len(cards), 6)]
    for number, chunk in enumerate(chunks, start=1):
        url = LIST_PATH if number == 1 else f'{LIST_PATH}?page={number}'
        pager = ''
        if number < len(chunks):
            pager = f'<ul class="pagination"><li><a class="page-link next" href="{LIST_PATH}?page={number + 1}" rel="next">›</a></li></ul>'
        pages[url] = f'<html><body><div class="row">{"".join(chunk)}</div>{pager}</body></html>'
    return pages


SITE = build_site()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = SITE.get(self.path)
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))

    def log_message(self, *args):
        pass


@pytest.fixture(scope='module')
def site():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}/'
    server.shutdown()


@pytest.fixture(scope='module')
def catalog(site):
    with LaptopScraper(site, delay=0) as scraper:
        return Catalog(scraper.scrape())


def test_scrape_all_pages(site):
    with LaptopScraper(site, delay=0) as scraper:
        laptops = list(scraper.scrape())
    assert len(laptops) == 117
    assert scraper.downloaded == 20
    assert laptops[0].title == 'Packard 255 G2' and laptops[0].brand == 'HP'


def test_paginator_is_an_iterator(site):
    with LaptopScraper(site, delay=0) as scraper:
        pages = Paginator(scraper, scraper.start_url)
        assert iter(pages) is pages
        first_url, _ = next(pages)
        second_url, _ = next(pages)
    assert first_url.endswith('/laptops') and second_url.endswith('?page=2')


def test_base_scraper_is_abstract():
    with pytest.raises(TypeError):
        BaseScraper()


def test_delay_cant_be_negative():
    scraper = LaptopScraper(delay=0)
    with pytest.raises(ValueError):
        scraper.delay = -1


def test_cache_read_write_delete(site, tmp_path):
    cache = PageCache(tmp_path / 'cache')
    with LaptopScraper(site, delay=0, cache=cache) as scraper:
        list(scraper.scrape())
    assert scraper.downloaded == 20 and len(cache) == 20

    with LaptopScraper(site, delay=0, cache=cache) as scraper:
        assert len(list(scraper.scrape())) == 117
    assert scraper.downloaded == 0 and scraper.from_cache == 20  # everything came from the files

    assert cache.clear() == 20
    assert len(cache) == 0


def test_cache_expires(tmp_path):
    cache = PageCache(tmp_path, max_age=timedelta(hours=1))
    url = 'https://webscraper.io/test-sites/e-commerce/static/computers/laptops?page=2'
    cache.save(url, '<html></html>')
    assert url in cache

    two_hours_ago = time.time() - 2 * 3600
    os.utime(cache._path(url), (two_hours_ago, two_hours_ago))
    assert url not in cache


def test_catalog(catalog):
    assert len(catalog) == 117
    assert catalog[0].price == 295.99 and catalog[-1].price == 1799
    assert catalog[0] in catalog
    assert len(Catalog(list(catalog) * 2)) == 117  # duplicates are dropped

    apple = catalog.filter(brand='apple')
    assert len(apple) == 3 and {l.specs.os for l in apple} == {('macOS',)}

    # these three have the description of a different laptop on the real site
    assert sorted(l.id for l in catalog.issues()) == [64, 97, 98]

    picks = catalog.filter(min_ram=16, ssd_only=True)
    assert len(picks) > 0
    assert all(l.specs.ram >= 16 and l.specs.has_ssd for l in picks)


def test_report(catalog):
    report = catalog.report()
    by_brand = report['By brand']
    assert by_brand['laptops'].sum() == 114  # 117 minus the 3 with the wrong description
    assert 'Other' not in set(by_brand['brand'])
    assert report['Price bands']['laptops'].sum() == 114
    assert list(report['Price bands']['price_band'])[0] == '$250 - $499'
    assert report['Best value (8GB+ SSD)']['price'].is_monotonic_increasing


def run_main(site, out, *args, stdin=None):
    return subprocess.run(
        [sys.executable, str(ROOT / 'main.py'), '--url', site, '--delay', '0', '--no-cache', '--out', str(out), *args],
        input=stdin, capture_output=True, text=True, check=True,
    )


def test_full_run(site, tmp_path):
    result = run_main(site, tmp_path)
    assert '117 laptops, 20 pages downloaded' in result.stdout

    wb = load_workbook(tmp_path / 'laptops.xlsx')
    assert wb.sheetnames == ['Laptops', 'By brand', 'By RAM', 'By CPU', 'Price bands',
                             'Avg price brand x RAM', 'Best value (8GB+ SSD)', 'Data issues']
    assert wb['Data issues'].max_row == 4
    assert wb['Laptops'].max_row == 118
    assert (tmp_path / 'chart.png').stat().st_size > 10_000
    assert (tmp_path / 'laptops.csv').exists()


def test_interactive(site, tmp_path):
    # 16GB RAM, max $1500, any brand, SSD only
    result = run_main(site, tmp_path, '--interactive', stdin='16\n1500\n\ny\n')
    assert 'laptops match' in result.stdout
    assert 'Your picks' in load_workbook(tmp_path / 'laptops.xlsx').sheetnames
