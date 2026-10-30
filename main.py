import argparse
import os
from datetime import timedelta

from catalog import Catalog
from scraper import BASE_URL, LaptopScraper, PageCache


def ask_number(question, cast):
    while True:
        answer = input(question).strip()
        if not answer:
            return None
        try:
            return cast(answer)
        except ValueError:
            print('  Please type a number, or press Enter to skip')


def ask_filters():
    print('\nFilter the laptops (press Enter to skip a question)')
    filters = {
        'min_ram': ask_number('Minimum RAM in GB: ', int),
        'max_price': ask_number('Maximum price in $: ', float),
        'brand': input('Brand, e.g. Dell: ').strip() or None,
        'ssd_only': input('SSD only? (y/n): ').strip().lower().startswith('y'),
    }
    return filters


def main():
    parser = argparse.ArgumentParser(description='Scrape the laptops from the webscraper.io test shop')
    parser.add_argument('--interactive', action='store_true', help='ask for filters after scraping')
    parser.add_argument('--delay', type=float, default=0.5, help='seconds between requests (default 0.5)')
    parser.add_argument('--cache-hours', type=float, default=24, help='reuse downloaded pages for this long (default 24)')
    parser.add_argument('--no-cache', action='store_true', help='always download the pages again')
    parser.add_argument('--clear-cache', action='store_true', help='delete the cached pages first')
    parser.add_argument('--out', default='output', help='output folder (default: output)')
    parser.add_argument('--url', default=BASE_URL, help='site url, mainly used by the tests')
    args = parser.parse_args()

    if args.clear_cache:
        print(f'Deleted {PageCache().clear()} cached pages')
    cache = None if args.no_cache else PageCache(max_age=timedelta(hours=args.cache_hours))

    with LaptopScraper(args.url, args.delay, cache) as scraper:
        catalog = Catalog(scraper.scrape())
        print(f'\n{len(catalog)} laptops, {scraper.downloaded} pages downloaded, {scraper.from_cache} read from the cache')

    print(f'Cheapest: {catalog[0]}')
    print(f'Most expensive: {catalog[-1]}')

    issues = catalog.issues()
    if issues:
        print(f'\n{len(issues)} products have the description of another laptop (left out of the stats):')
        for laptop in issues:
            print(f'  #{laptop.id} {laptop.title}: "{laptop.description[:45]}..."')

    picks = None
    if args.interactive:
        picks = catalog.filter(**ask_filters())
        print(f'\n{len(picks)} laptops match:')
        for laptop in picks[:10]:
            print(f'  {laptop}')
        if len(picks) > 10:
            print(f'  ... and {len(picks) - 10} more in the Excel file')

    os.makedirs(args.out, exist_ok=True)
    catalog.to_frame().to_csv(os.path.join(args.out, 'laptops.csv'), index=False, encoding='utf-8-sig')
    catalog.save_excel(os.path.join(args.out, 'laptops.xlsx'), picks)
    catalog.save_chart(os.path.join(args.out, 'chart.png'))
    print(f'\nSaved laptops.xlsx, laptops.csv and chart.png to {args.out}/')


if __name__ == '__main__':
    main()
