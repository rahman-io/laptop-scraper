import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

# The descriptions are free text typed by hand, e.g.
#   'Lenovo Legion Y520-15IKBM, Black, 15.6" FHD IPS, Core i5-7300HQ, 8 GB, 128GB SSD + 2 TB HDD,
#    NVIDIA GeForce GTX 1060 6 GB, FreeDOS + Windows 10 Home'
# so every part is pulled out with its own pattern, left to right.

SCREEN = re.compile(r'(?P<size>\d{2}(?:\.\d)?)",?(?:\s?(?P<res>UHD|FHD|HD\+?))?(?P<extra>(?:\s(?:IPS|Touch|120Hz))*)')

CPU = re.compile(r'''
    (?P<cpu>
        (?:Intel\s)?Core\s?i[3579](?:[-\s]\d{4}[A-Z]*)?   # Core i5-7200U, Core i5 4200U, Core i5
      | \bi[3579](?=\s\d)                               # MacBook: "i5 1.8GHz"
      | Celeron,?\s?N?\d{4}[A-Z]?                        # Celeron N3350, "Celeron, N3350", Celeron 3855U
      | Pentium\sN\d{4}
      | AMD\s[AE]\d-\d{4}
      | Ryzen\s\d\s\d{4}
    )
    (?:\s(?P<ghz>\d\.\d+)\s?GHz)?
''', re.VERBOSE)

INTEL_MODEL = re.compile(r'i[3579]-(?P<gen>\d)\d{3}(?P<suffix>[A-Z]*)')

RAM = re.compile(r'(?P<ram>\d{1,2})\s?GB(?:\sDDR\dL?)?')

DRIVE = r'\d+\s?[GT]B(?:\s?(?:SSD|HDD|SSHD|eMMC))?(?:\s?Cache)?'
STORAGE = re.compile(rf'{DRIVE}(?:\s?\+\s?{DRIVE})*')
DRIVE_PARTS = re.compile(r'(?P<size>\d+)\s?(?P<unit>[GT]B)(?:\s?(?P<kind>SSD|HDD|SSHD|eMMC))?(?P<cache>\s?Cache)?')

GPU = re.compile(r'''
    (?P<gpu>
        (?:NVIDIA\s)?GeForce\s[\w\s-]+?
      | GTX\s\d{3,4}(?:\s?Ti)?
      | Radeon\s[\w\s]+?
      | Intel\sHD\s\d{4}
      | Iris\sPlus\s\d{3}
    )
    (?:\s(?P<vram>\d+)\s?GB)?
    (?=,|$)
''', re.VERBOSE)

OS = re.compile(r'\b(?:Windows(?:\s\d+(?:\.\d)?)?(?:\s(?:Home|Pro))?|Win7\sPro|Linux|Endless\sOS|FreeDOS|DOS|No\sOS)\b')

BRANDS = {
    'HP': r'\b(?:HP|Hewlett|Packard|ProBook|Pavilion|Spectre)\b',
    'Lenovo': r'\b(?:Lenovo|ThinkPad|Legion|IdeaPad|Yoga)\b',
    'Acer': r'\b(?:Acer|Aspire|Nitro|Swift|Extensa|TravelMate|Predator)\b',
    'Dell': r'\b(?:Dell|Inspiron|Vostro|Latitude|XPS)\b',
    'Asus': r'\b(?:Asus|VivoBook|ROG|ZenBook|EeeBook)\b',
    'Apple': r'\b(?:Apple|MacBook)\b',
    'MSI': r'\bMSI\b',
    'Toshiba': r'\b(?:Toshiba|Portege)\b',
    'Prestigio': r'\bPrestigio\b',
}
BRAND_PATTERNS = {brand: re.compile(pattern, re.IGNORECASE) for brand, pattern in BRANDS.items()}


def clean_cpu(raw):
    cpu = re.sub(r',?\s+', ' ', raw)                 # "Celeron, N3350" -> "Celeron N3350"
    cpu = cpu.removeprefix('Intel ')
    cpu = re.sub(r'^(i\d)$', r'Core \1', cpu)        # MacBook "i5" -> "Core i5"
    return re.sub(r'(i\d) (\d{4})', r'\1-\2', cpu)   # "Core i5 4200U" -> "Core i5-4200U"


def normalize_os(name):
    match name.split():
        case ['Windows', version, *_]:
            return f'Windows {version}'
        case ['Windows']:
            return 'Windows'
        case ['Win7', *_]:
            return 'Windows 7'
        case ['Linux'] | ['Endless', 'OS']:
            return 'Linux'
        case _:
            return 'No OS'  # DOS, FreeDOS, No OS


def size_label(gb):
    return f'{gb // 1000}TB' if gb >= 1000 else f'{gb}GB'


@dataclass(eq=False)
class Laptop:
    id: int
    title: str
    price: float
    description: str
    rating: int
    reviews: int
    url: str
    specs: 'Laptop.Specs' = field(init=False, repr=False)

    @dataclass
    class Specs:
        screen: float | None = None
        resolution: str | None = None
        touch: bool = False
        ips: bool = False
        cpu: str | None = None
        cpu_ghz: float | None = None
        cpu_gen: int | None = None
        ram: int | None = None
        drives: tuple = ()  # ((128, 'SSD'), (1000, 'HDD'))
        gpu: str = 'Integrated'
        vram: int | None = None
        os: tuple = ()

        @classmethod
        def from_text(cls, text):
            specs = cls()
            pos = 0  # each search starts where the previous one ended

            if m := SCREEN.search(text):
                specs.screen = float(m['size'])
                specs.resolution = m['res']
                specs.touch = 'Touch' in m['extra']
                specs.ips = 'IPS' in m['extra']
                pos = m.end()

            if m := CPU.search(text, pos):
                specs.cpu = clean_cpu(m['cpu'])
                specs.cpu_ghz = float(m['ghz']) if m['ghz'] else None
                if model := INTEL_MODEL.search(specs.cpu):
                    specs.cpu_gen = int(model['gen'])
                pos = m.end()

            if m := RAM.search(text, pos):
                specs.ram = int(m['ram'])
                pos = m.end()

            if m := STORAGE.search(text, pos):
                drives = []
                for drive in DRIVE_PARTS.finditer(m.group()):
                    if drive['cache']:
                        continue  # "16GB SSD Cache" isn't real storage
                    size = int(drive['size']) * (1000 if drive['unit'] == 'TB' else 1)
                    # most descriptions skip the type for hard drives ("500GB", "1TB"),
                    # for the small ones we can't tell
                    kind = drive['kind'] or ('HDD' if size >= 500 else 'unknown')
                    drives.append((size, kind))
                specs.drives = tuple(drives)
                pos = m.end()

            if m := GPU.search(text, pos):
                specs.gpu = m['gpu'].strip()
                specs.vram = int(m['vram']) if m['vram'] else None

            found = [normalize_os(name) for name in OS.findall(text, pos)]
            specs.os = tuple(dict.fromkeys(found))  # unique, keeps the order
            if not specs.os and 'MacBook' in text:
                specs.os = ('macOS',)
            return specs

        @property
        def cpu_family(self):
            if not self.cpu:
                return 'Unknown'
            match self.cpu.split():
                case ['Core', model, *_]:
                    return f'Intel Core {model[:2]}'
                case ['Celeron' | 'Pentium' as name, *_]:
                    return f'Intel {name}'
                case ['Ryzen', tier, *_]:
                    return f'AMD Ryzen {tier}'
                case ['AMD', model]:
                    return f'AMD {model.split("-")[0]}'
                case _:
                    return 'Other'

        @property
        def gpu_vendor(self):
            match self.gpu.split()[0]:
                case 'GeForce' | 'NVIDIA' | 'GTX':
                    return 'NVIDIA'
                case 'Radeon':
                    return 'AMD'
                case 'Intel' | 'Iris':
                    return 'Intel'
                case _:
                    return None  # integrated graphics, not named in the description

        @property
        def storage_gb(self):
            return sum(size for size, _ in self.drives)

        @property
        def has_ssd(self):
            return any(kind == 'SSD' for _, kind in self.drives)

    def __post_init__(self):
        self.specs = self.Specs.from_text(self.description)

    @classmethod
    def from_card(cls, card, page_url):
        link = card.select_one('a.title')
        url = urljoin(page_url, link['href'])
        return cls(
            id=int(re.search(r'/product/(\d+)', url)[1]),
            title=link['title'].strip(),  # the link text is cut off on long names
            price=float(card.select_one('[itemprop=price]').text.strip().lstrip('$').replace(',', '')),
            description=card.select_one('p.description').text.strip(),
            rating=int(card.select_one('[data-rating]')['data-rating']),
            reviews=int(card.select_one('[itemprop=reviewCount]').text),
            url=url,
        )

    @staticmethod
    def find_brand(text):
        for brand, pattern in BRAND_PATTERNS.items():
            if pattern.search(text):
                return brand
        return None

    @property
    def brand(self):
        # not every title has the brand in it ("ThinkPad T540p", "ProBook"), so model names count too
        return self.find_brand(self.title) or self.find_brand(self.description) or 'Other'

    @property
    def mismatch(self):
        # A few products on the site have the description of another laptop, e.g.
        # "Asus ROG Strix GL553VD-DM535T" with "Apple MacBook Air 13.3", Core i5 1.8GHz, ..."
        described = self.find_brand(self.description)
        return described is not None and described != self.brand

    def __eq__(self, other):
        return isinstance(other, Laptop) and self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __lt__(self, other):
        return (self.price, self.title) < (other.price, other.title)

    def __str__(self):
        s = self.specs
        storage = ' + '.join(f'{size_label(size)} {kind}' for size, kind in s.drives)
        return f'{self.title} (${self.price:,.2f}): {s.cpu}, {s.ram}GB RAM, {storage}'

    def to_dict(self):
        s = self.specs
        return {
            'id': self.id,
            'brand': self.brand,
            'title': self.title,
            'price': self.price,
            'screen': s.screen,
            'resolution': s.resolution,
            'touch': s.touch,
            'cpu': s.cpu,
            'cpu_family': s.cpu_family,
            'cpu_gen': s.cpu_gen,
            'ram_gb': s.ram,
            'storage_gb': s.storage_gb,
            'storage': ' + '.join(f'{size_label(size)} {kind}' for size, kind in s.drives),
            'ssd': s.has_ssd,
            'gpu': s.gpu,
            'gpu_vendor': s.gpu_vendor,
            'vram_gb': s.vram,
            'os': ', '.join(s.os),
            'rating': self.rating,
            'reviews': self.reviews,
            'description_mismatch': self.mismatch,
            'description': self.description,
            'url': self.url,
        }
