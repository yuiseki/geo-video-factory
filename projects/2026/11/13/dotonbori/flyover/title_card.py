"""Reusable silent chapter cards for the chapter rendering pipeline."""
import subprocess
from PIL import Image, ImageDraw, ImageFont

FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'


def create_card(title, section, output, series='YuisekinTV'):
    image = Image.new('RGB', (1920, 1080), '#101c2e')
    d = ImageDraw.Draw(image)
    small = ImageFont.truetype(FONT, 36)
    big = ImageFont.truetype(FONT, 72)
    d.text((960, 350), series, font=small, anchor='mm', fill='#e7b462')
    d.text((960, 455), f'第 {section} 章', font=small, anchor='mm', fill='#d5e0ed')
    d.text((960, 560), title, font=big, anchor='mm', fill='white')
    d.line((600, 650, 1320, 650), fill='#e7b462', width=4)
    image.save(output)


def encode_card(image, output, *, fps=24, seconds=2.5):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-loop', '1', '-framerate', str(fps),
                    '-i', str(image), '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
                    '-t', str(seconds), '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                    '-crf', '18', '-maxrate', '20M', '-bufsize', '40M', '-profile:v', 'high', '-level:v', '4.1',
                    '-g', str(fps * 2), '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', str(output)],
                   check=True)
