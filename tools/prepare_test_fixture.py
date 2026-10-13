"""Download one public, pinned model example into the ignored QA folder."""
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

URL = 'https://raw.githubusercontent.com/xuebinqin/U-2-Net/ac7e1c817ecab7c7dff5ce6b1abba61cd213ff29/test_data/test_images/horse.jpg'
EXPECTED = 'ef7a90ef39ae6265db3ad9c03cf9a6f1ff7be3b3fe11b203ae05e300b7d8aaa1'
target = Path(__file__).resolve().parents[1] / '.qa' / 'fixtures' / 'u2net-horse.jpg'
if target.is_file():
    data = target.read_bytes()
else:
    with urlopen(URL, timeout=30) as response:
        data = response.read()
if sha256(data).hexdigest() != EXPECTED:
    raise RuntimeError('The model example checksum does not match the pinned fixture.')
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(data)
print(f'Public model example verified: {target}')
