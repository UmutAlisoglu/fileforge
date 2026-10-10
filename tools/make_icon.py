"""Generate the Windows icon from FileForge's simple geometric logo."""
from pathlib import Path
from PIL import Image, ImageDraw

scale = 4
image = Image.new("RGBA", (256 * scale, 256 * scale))
draw = ImageDraw.Draw(image)
def box(values):
    return tuple(value * scale for value in values)
draw.rounded_rectangle(box((8, 8, 248, 248)), radius=66 * scale, fill="#c8f27b")
draw.polygon([(x * scale, y * scale) for x, y in [(78,184),(78,74),(162,74),(162,99),(107,99),(107,120),(150,120),(150,145),(107,145),(107,184)]], fill="#192323")
draw.line([(146*scale,185*scale),(193*scale,138*scale)], fill="#192323", width=15*scale)
draw.line([(163*scale,138*scale),(193*scale,138*scale),(193*scale,168*scale)], fill="#192323", width=15*scale, joint="curve")
image = image.resize((256, 256), Image.Resampling.LANCZOS)
root = Path(__file__).resolve().parents[1]
image.save(root / "assets/fileforge.ico", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
