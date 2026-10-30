import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from laptop import Laptop

HERE = Path(__file__).parent

# real descriptions from the site, including the messy ones
CASES = [
    ('15.6", AMD E2-3800 1.3GHz, 4GB, 500GB, Windows 8.1',
     dict(screen=15.6, cpu='AMD E2-3800', cpu_family='AMD E2', cpu_ghz=1.3, ram=4,
          drives=((500, 'HDD'),), gpu='Integrated', os=('Windows 8.1',))),

    ('12.5" Touch, Core i3-4010U, 4GB, 500GB + 16GB SSD Cache,',
     dict(touch=True, cpu='Core i3-4010U', cpu_gen=4, ram=4, drives=((500, 'HDD'),), os=())),

    ('12.5" Touch, Core i5 4200U, 8GB, 500GB + 16GB SSD Cache, Windows',
     dict(cpu='Core i5-4200U', os=('Windows',))),

    ('Acer Aspire ES1-732 Black, 17.3" HD+, Celeron, N3350, 4GB, 1TB, Windows 10 Home',
     dict(screen=17.3, resolution='HD+', cpu='Celeron N3350', cpu_family='Intel Celeron', ram=4,
          drives=((1000, 'HDD'),), os=('Windows 10',))),

    ('Acer Aspire 3 A315-21, 15.6", AMD A4-9120. 4GB. 128GB SSD, Linux',
     dict(cpu='AMD A4-9120', cpu_family='AMD A4', ram=4, drives=((128, 'SSD'),), os=('Linux',))),

    ('Acer Aspire A315-31-C33J Black 15.6", HD, Celeron N3350, 4GB DDR3L, 128GB, Windows 10 Home, ENG',
     dict(resolution='HD', ram=4, drives=((128, 'unknown'),))),

    ('Lenovo Legion Y520-15IKBM, Black, 15.6" FHD IPS, Core i5-7300HQ, 8 GB, 128GB SSD + 2 TB HDD, '
     'NVIDIA GeForce GTX 1060 6 GB, FreeDOS + Windows 10 Home',
     dict(resolution='FHD', ips=True, cpu='Core i5-7300HQ', cpu_gen=7, ram=8,
          drives=((128, 'SSD'), (2000, 'HDD')), gpu='NVIDIA GeForce GTX 1060', vram=6,
          os=('No OS', 'Windows 10'))),

    ('Asus ROG Strix SCAR Edition GL503VM-ED115T, 15.6" FHD 120Hz, Core i7-7700HQ, 16GB, '
     '256GB SSD + 1TB SSHD, GeForce GTX 1060 6GB, Windows 10 Home',
     dict(cpu_family='Intel Core i7', ram=16, drives=((256, 'SSD'), (1000, 'SSHD')),
          gpu='GeForce GTX 1060', vram=6)),

    ('Asus ROG Strix GL702ZC-GC154T, 17.3" FHD, Ryzen 7 1700, 16GB, 256GB + 1TB HDD, Radeon RX 580 4GB, '
     'Windows 10 Home',
     dict(cpu='Ryzen 7 1700', cpu_family='AMD Ryzen 7', drives=((256, 'unknown'), (1000, 'HDD')),
          gpu='Radeon RX 580', vram=4)),

    ('Moon Silver, 15.6", Core i7-4510U, 8GB, 1TB, Radeon HD R7 M265 2GB,',
     dict(gpu='Radeon HD R7 M265', vram=2, os=())),

    ('Lenovo Legion Y520, 15.6" FHD, Core i7-7700HQ, 8GB, 128 GB SSD + 1TB HDD, GTX 1050 4GB, Windows 10 Home',
     dict(drives=((128, 'SSD'), (1000, 'HDD')), gpu='GTX 1050', vram=4)),

    ('Apple MacBook Air 13", i5 1.8GHz, 8GB, 256GB SSD, Intel HD 6000, ENG',
     dict(screen=13.0, resolution=None, cpu='Core i5', cpu_ghz=1.8, gpu='Intel HD 6000', os=('macOS',))),

    ('Prestigio SmartBook 133S Gold, 13.3" FHD IPS, Celeron N3350 1.1GHz, 4GB, 32GB, '
     'Windows 10 Pro + Office 365 1 gadam',
     dict(ram=4, drives=((32, 'unknown'),), os=('Windows 10',))),
]


@pytest.mark.parametrize('text, expected', CASES)
def test_specs(text, expected):
    specs = Laptop.Specs.from_text(text)
    for name, value in expected.items():
        assert getattr(specs, name) == value, name


def test_every_description_on_the_site():
    lines = (HERE / 'descriptions.txt').read_text(encoding='utf-8').splitlines()
    assert len(lines) == 117
    for line in lines:
        specs = Laptop.Specs.from_text(line)
        assert specs.screen and specs.cpu and specs.ram and specs.drives, line
        assert specs.cpu_family not in ('Other', 'Unknown'), line


def make_laptop(id, title, price, description='15.6", Core i5-7200U, 8GB, 256GB SSD, Windows 10 Home'):
    return Laptop(id=id, title=title, price=price, description=description, rating=3, reviews=1,
                  url=f'https://example.com/product/{id}')


@pytest.mark.parametrize('title, brand', [
    ('ThinkPad T540p', 'Lenovo'),
    ('ProBook', 'HP'),
    ('Packard 255 G2', 'HP'),
    ('Aspire E1-510', 'Acer'),
    ('Inspiron 15', 'Dell'),
    ('Asus ASUSPRO B9440UA-GV0279R Gray', 'Asus'),
    ('Toshiba Portege Z30-C-16J Grey', 'Toshiba'),
])
def test_brand(title, brand):
    assert make_laptop(1, title, 500).brand == brand


def test_description_of_another_laptop():
    laptop = make_laptop(98, 'Asus ROG Strix GL553VD-DM535T', 1101.83,
                         'Apple MacBook Air 13.3", Core i5 1.8GHz, 8GB, 128GB SSD, Intel HD 4000, RUS')
    assert laptop.brand == 'Asus'
    assert laptop.mismatch
    assert not make_laptop(1, 'Dell Latitude 5480', 1110.14).mismatch


def test_magic_methods():
    cheap = make_laptop(1, 'Aspire E1-510', 306.99)
    pricey = make_laptop(2, 'ThinkPad X240', 1311.99)
    same_product = make_laptop(1, 'Aspire E1-510', 306.99)

    assert cheap == same_product and cheap != pricey
    assert len({cheap, pricey, same_product}) == 2
    assert sorted([pricey, cheap]) == [cheap, pricey]
    assert str(cheap) == 'Aspire E1-510 ($306.99): Core i5-7200U, 8GB RAM, 256GB SSD'
