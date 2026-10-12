#!/usr/bin/env bash
# Turn docs/demo/raw.webm into docs/demo/demo.mp4 and docs/demo/demo.gif.
# Only the wait for the model (between the "asked" and "answered" marks) is sped up, and a caption says so.
set -euo pipefail
cd "$(dirname "$0")/../../docs/demo"
asked=$(python3 -c "import json;print(json.load(open('marks.json'))['asked'])")
answered=$(python3 -c "import json;print(json.load(open('marks.json'))['answered'])")
wait_s=$(python3 -c "print(round($answered - $asked))")
speed=${SPEED:-12}
caption="${CAPTION:-sped up ${speed}x - ${wait_s}s on a local 8B model on a laptop}"

# Caption bar as an image (works with ffmpeg builds that lack the drawtext filter). Needs Pillow.
PYTHON=${PYTHON:-../../backend/.venv/bin/python}
"$PYTHON" - "$caption" <<'PY'
import sys
from PIL import Image, ImageDraw, ImageFont
text = sys.argv[1]
bar = Image.new("RGBA", (1280, 44), (0, 0, 0, 170))
draw = ImageDraw.Draw(bar)
try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
except OSError:
    font = ImageFont.load_default()
width = draw.textlength(text, font=font)
draw.text(((1280 - width) / 2, 11), text, font=font, fill=(255, 255, 255, 255))
bar.save("caption.png")
PY

ffmpeg -y -loglevel error -i raw.webm -i caption.png -filter_complex "
  [0:v]trim=0:${asked},setpts=PTS-STARTPTS[a];
  [0:v]trim=${asked}:${answered},setpts=(PTS-STARTPTS)/${speed}[w];
  [w][1:v]overlay=0:H-h[b];
  [0:v]trim=${answered},setpts=PTS-STARTPTS[c];
  [a][b][c]concat=n=3:v=1:a=0,fps=30,format=yuv420p[v]" \
  -map "[v]" -c:v libx264 -crf 23 -movflags +faststart demo.mp4

ffmpeg -y -loglevel error -i demo.mp4 -vf "fps=10,scale=960:-1:flags=lanczos,palettegen=stats_mode=diff" palette.png
ffmpeg -y -loglevel error -i demo.mp4 -i palette.png \
  -lavfi "fps=10,scale=960:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4" demo.gif
rm -f palette.png caption.png
ls -lh demo.mp4 demo.gif
