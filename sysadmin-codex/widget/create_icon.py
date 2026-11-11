"""Genera un'icona vettoriale rasterizzata a più risoluzioni per Windows."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent
size = 1024
img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((28, 28, 996, 996), radius=230, fill=(19, 33, 46, 255))
d.rounded_rectangle((43, 43, 981, 981), radius=215, outline=(83, 104, 120, 255), width=8)
# Un anello incompleto richiama progresso e continuità; la griglia è il calendario.
d.arc((174, 174, 850, 850), 205, 515, fill=(246, 162, 122, 255), width=86)
for angle in (205, 515):
    import math
    x = 512 + 295*math.cos(math.radians(angle))
    y = 512 + 295*math.sin(math.radians(angle))
    d.ellipse((x-43, y-43, x+43, y+43), fill=(246, 162, 122, 255))
for row in range(3):
    for col in range(3):
        x, y = 366+col*107, 366+row*107
        color = (255, 197, 163, 255) if (row,col) in ((0,2),(1,1),(2,0),(2,2)) else (98, 118, 131, 255)
        d.rounded_rectangle((x,y,x+72,y+72), radius=15, fill=color)
png = img.resize((256, 256), Image.Resampling.LANCZOS)
png.save(ROOT / 'app-icon.png')
img.save(ROOT / 'app-icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
