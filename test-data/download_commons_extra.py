from __future__ import annotations
import hashlib
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

OUT = pathlib.Path('/tmp/commons-extra')
ITEMS = [
    ('kettle-le18c', 'Kettle_DSC06001.jpg', 'Kettle, Le dynasty, 18th century AD, bronze - Museum of Vietnamese History - Ho Chi Minh City - DSC06001.JPG'),
    ('kettle-le18c', 'Kettle_DSC06002.jpg', 'Kettle, Le dynasty, 18th century AD, bronze - Museum of Vietnamese History - Ho Chi Minh City - DSC06002.JPG'),
    ('kettle-le18c', 'Kettle_DSC06003.jpg', 'Kettle, Le dynasty, 18th century AD, bronze - Museum of Vietnamese History - Ho Chi Minh City - DSC06003.JPG'),
    ('dong-son-bell', 'Dong_Son_Bell_01.jpg', 'Collections of the Museum of Vietnamese History Dong Son culture Bell(Bronze) 01.jpg'),
    ('dong-son-bell', 'Dong_Son_Bell_02.jpg', 'Collections of the Museum of Vietnamese History Dong Son culture Bell(Bronze) 02.jpg'),
    ('dong-son-bell', 'Dong_Son_Bell_03.jpg', 'Collections of the Museum of Vietnamese History Dong Son culture Bell(Bronze) 03.jpg'),
]
OUT.mkdir(parents=True, exist_ok=True)
for index, (folder, output, original) in enumerate(ITEMS):
    normalized = original.replace(' ', '_')
    digest = hashlib.md5(normalized.encode('utf-8')).hexdigest()
    encoded = urllib.parse.quote(normalized, safe="()!,.-_")
    url = f'https://upload.wikimedia.org/wikipedia/commons/thumb/{digest[0]}/{digest[:2]}/{encoded}/960px-{encoded}'
    target_dir = OUT / folder
    target_dir.mkdir(exist_ok=True)
    target = target_dir / output
    if not target.exists():
        request = urllib.request.Request(url, headers={'User-Agent': 'SMGS-AIVision-test/1.0 (educational prototype)'})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    if response.status != 200:
                        raise RuntimeError(f'HTTP {response.status}')
                    content = response.read()
                if len(content) < 10000:
                    raise RuntimeError(f'Unexpected small response: {len(content)} bytes')
                target.write_bytes(content)
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 3:
                    time.sleep(20 * (attempt + 1))
                    continue
                raise RuntimeError(f'HTTP {exc.code} for Commons file') from None
        else:
            raise RuntimeError(f'Failed to download {original}')
    print(f'{folder}/{output}: {target.stat().st_size} bytes')
    if index < len(ITEMS) - 1:
        time.sleep(8)
