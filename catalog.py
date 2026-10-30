import math

import matplotlib
matplotlib.use('Agg')  # we only save the chart to a file, no window needed
import matplotlib.pyplot as plt
import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


def price_band(price, size=250):
    low = math.floor(price / size) * size
    return f'${low:,} - ${low + size - 1:,}'


class Catalog:
    def __init__(self, laptops):
        # set() drops duplicate products (Laptop.__hash__ uses the product id),
        # sorted() uses Laptop.__lt__, so the list goes from cheapest to most expensive
        self._laptops = sorted(set(laptops))

    def __len__(self):
        return len(self._laptops)

    def __iter__(self):
        return iter(self._laptops)

    def __getitem__(self, index):
        return self._laptops[index]

    def __contains__(self, laptop):
        return laptop in self._laptops

    def __repr__(self):
        return f'Catalog({len(self)} laptops)'

    def filter(self, min_ram=None, max_price=None, brand=None, ssd_only=False):
        matches = []
        for laptop in self:
            if min_ram and (laptop.specs.ram or 0) < min_ram:
                continue
            if max_price and laptop.price > max_price:
                continue
            if brand and laptop.brand.lower() != brand.lower():
                continue
            if ssd_only and not laptop.specs.has_ssd:
                continue
            matches.append(laptop)
        return Catalog(matches)

    def to_frame(self):
        df = pd.DataFrame([laptop.to_dict() for laptop in self])
        if not df.empty:
            df['price_band'] = df['price'].apply(price_band)
        return df

    def issues(self):
        return [laptop for laptop in self if laptop.mismatch]

    def report(self):
        df = self.to_frame()
        # the specs of these come from another laptop's description, so they'd skew the numbers
        df = df[~df['description_mismatch']]

        by_brand = (
            df.groupby('brand')
            .agg(laptops=('id', 'count'), avg_price=('price', 'mean'), min_price=('price', 'min'),
                 max_price=('price', 'max'), avg_rating=('rating', 'mean'))
            .round(2)
            .sort_values('laptops', ascending=False)
            .reset_index()
        )
        by_ram = (
            df.groupby('ram_gb')
            .agg(laptops=('id', 'count'), avg_price=('price', 'mean'), median_price=('price', 'median'))
            .round(2)
            .reset_index()
        )
        by_cpu = (
            df.groupby('cpu_family')
            .agg(laptops=('id', 'count'), avg_price=('price', 'mean'), avg_ram_gb=('ram_gb', 'mean'))
            .round(2)
            .sort_values('avg_price')
            .reset_index()
        )
        # price bands sorted by the lowest price in the band, not alphabetically
        bands = df.assign(low=df['price'] // 250).groupby(['low', 'price_band']).size()
        bands = bands.reset_index(name='laptops').drop(columns='low')

        brand_ram = pd.pivot_table(df, values='price', index='brand', columns='ram_gb', aggfunc='mean').round(0)
        brand_ram.columns = [f'{gb}GB' for gb in brand_ram.columns]

        best_value = (
            df[(df['ram_gb'] >= 8) & df['ssd']]
            .nsmallest(10, 'price')[['title', 'brand', 'price', 'cpu', 'ram_gb', 'storage', 'gpu', 'os']]
        )

        return {
            'By brand': by_brand,
            'By RAM': by_ram,
            'By CPU': by_cpu,
            'Price bands': bands,
            'Avg price brand x RAM': brand_ram,
            'Best value (8GB+ SSD)': best_value,
        }

    def save_excel(self, path, picks=None):
        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            self.to_frame().to_excel(writer, sheet_name='Laptops', index=False)
            if picks is not None:
                picks.to_frame().to_excel(writer, sheet_name='Your picks', index=False)
            for name, table in self.report().items():
                # the pivot table keeps brand names in its index, the others don't need one
                table.to_excel(writer, sheet_name=name, index=name.startswith('Avg price'))

            issues = pd.DataFrame(
                [(l.id, l.title, l.brand, l.find_brand(l.description), l.description, l.url) for l in self.issues()],
                columns=['id', 'title', 'brand in title', 'brand in description', 'description', 'url'],
            )
            if not issues.empty:
                issues.to_excel(writer, sheet_name='Data issues', index=False)

            for ws in writer.book.worksheets:
                style_sheet(ws)

    def save_chart(self, path):
        report = self.report()
        by_ram = report['By RAM']
        by_brand = report['By brand'].sort_values('avg_price')

        fig, (left, right) = plt.subplots(1, 2, figsize=(13, 5.5))

        bars = left.bar([f'{gb}GB' for gb in by_ram['ram_gb']], by_ram['avg_price'], color='#305496')
        left.bar_label(bars, labels=[f'${p:,.0f}' for p in by_ram['avg_price']], padding=3)
        left.set_title('Average price by RAM')
        left.set_ylabel('USD')

        bars = right.barh(by_brand['brand'], by_brand['avg_price'], color='#f5a524')
        right.bar_label(bars, labels=[f'${p:,.0f} ({n})' for p, n in zip(by_brand['avg_price'], by_brand['laptops'])],
                        padding=3)
        right.set_title('Average price by brand (number of laptops)')
        right.set_xlim(0, by_brand['avg_price'].max() * 1.25)

        for ax in (left, right):
            ax.spines[['top', 'right']].set_visible(False)

        laptops = report['By brand']['laptops'].sum()
        fig.suptitle(f'{laptops} laptops from the webscraper.io test shop', fontsize=14)
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)


def style_sheet(ws):
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='305496')
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions

    for column in ws.columns:
        longest = max(len(str(cell.value)) for cell in column if cell.value is not None)
        ws.column_dimensions[get_column_letter(column[0].column)].width = min(longest + 2, 60)
