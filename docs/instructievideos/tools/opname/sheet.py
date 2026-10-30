#!/usr/bin/env python3
"""sheet.py NN [scene ...] — contact sheet with 2 frames (40% and 90%) of each recorded scene."""
import glob, os, subprocess, sys
from PIL import Image, ImageDraw
nn = sys.argv[1]; only = sys.argv[2:]
clips = sorted(glob.glob(f'/opt/rec/out/{nn}/s*.mp4'))
if only: clips = [c for c in clips if os.path.basename(c)[:-4] in only]
tiles = []
for c in clips:
    d = float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',c],capture_output=True,text=True).stdout)
    for f in (0.4, 0.9):
        out = f'/tmp/sheet_{os.path.basename(c)}_{f}.png'
        subprocess.run(['ffmpeg','-loglevel','error','-y','-ss',str(d*f),'-i',c,'-frames:v','1','-vf','scale=640:-1',out],check=True)
        im = Image.open(out); ImageDraw.Draw(im).text((8,8), f'{os.path.basename(c)} {f:.0%}', fill=(255,0,0)); tiles.append(im)
w,h = tiles[0].size; cols = 4
g = Image.new('RGB',(w*cols,h*((len(tiles)+cols-1)//cols)),'white')
for i,t in enumerate(tiles): g.paste(t,((i%cols)*w,(i//cols)*h))
g.save(f'/opt/rec/out/{nn}/sheet.png'); print(f'/opt/rec/out/{nn}/sheet.png')
