#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daily Instagram package generator for horror manga 『盛り塩の家』.

Scheduled at 09:00 JST by GitHub Actions.
Outputs per day:
- 5 numbered vertical PNG storyboard images: DAYxx_1of5.png ... DAYxx_5of5.png
- 5 prompt text files for final manga image generation
- 1 Instagram caption text file
- 1 JSON package
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

SERIES = "盛り塩の家"
START_DATE_DEFAULT = "2026-06-26"
CAST = "Aたくや=主人公 / Bもとや=分析役 / Cかえて=感情の中心 / Dばやし=ムードメーカー。KRUMP要素なし。"

DAY_TITLES = [
    "朝の盛り塩", "誰が置いた", "郵便受け", "塩をどけるな", "この家",
    "玄関の内側", "名前を呼ぶ声", "塩の線", "受理", "壁の向こう",
    "壁の中", "白い粉", "前の住人", "押入れ", "一人目",
    "空室の中", "十五年前", "返し忘れ", "母の声", "聞こえた",
    "侵入", "五人目", "写真", "家を出るな", "役割",
    "盛り塩の意味", "家の心臓", "拒む者", "最後の盛り塩", "空室",
]

ARC_LINES = [
    "玄関前の白い盛り塩が、4人の日常に最初の違和感を残す。",
    "監視しても誰も来ないのに、塩だけが少しずつ増える。",
    "郵便受けに細い紙が入り、文字の意味を追い始める。",
    "隣人の警告で、塩が嫌がらせではない可能性が出る。",
    "古い地域ログから、この部屋が何かに選ばれたと分かる。",
    "盛り塩が玄関の内側に現れ、何かが中に入ったと分かる。",
    "部屋の中から大切な人の声がして、返事をしてはいけないルールが示される。",
    "塩の線を越えたばやしに印が残り、順番が始まる。",
    "紙を処分しようとしても、家はそれを受け取ったことにしてしまう。",
    "空室のはずの隣から生活音が聞こえ、壁の向こうに同じ部屋が現れる。",
    "壁の内側から開けてほしい声が続き、鍵穴が現れる。",
    "部屋の白い粉が、盛り塩とは別のものだと分かる。",
    "前の住人の記録が消えており、同じ現象が繰り返されていたと分かる。",
    "なかったはずの押入れに、かえての過去につながる物が入っている。",
    "ばやしの存在が少しずつ薄くなり、部屋が空室扱いになる。",
    "空室の中で、過去に選ばれた家の痕跡を見つける。",
    "十五年前、かえてがこの現象に関わっていた可能性が浮かぶ。",
    "返し忘れた紙のせいで、家が今の部屋まで追ってきたと分かる。",
    "かえての前に母の声が現れ、返事をしてしまいそうになる。",
    "返事をきっかけに、見えないものが部屋に入り始める。",
    "茶碗、歯ブラシ、椅子が一つ増え、見えない同居人が定着し始める。",
    "五人目に名前をつけてはいけないという新しいルールが出る。",
    "明日撮られるはずの集合写真が現れ、完成すると出られないと分かる。",
    "外へ出ようとしても同じ部屋に戻され、家そのものに閉じ込められる。",
    "4人それぞれに役割が与えられ、たくやが返す者だと示される。",
    "盛り塩は封じるものではなく、帰る道を示すものだと分かる。",
    "床下の奥に家の中心があり、そこへ塩を返す必要がある。",
    "かえてが過去の声を拒み、4人が役割を果たし始める。",
    "たくやが最後の盛り塩を置くが、家が最後の抵抗をする。",
    "朝、部屋は元に戻る。しかし次の家を示す紙だけが残る。",
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default=os.environ.get("MORISHIO_START_DATE", START_DATE_DEFAULT))
    parser.add_argument("--manual-day", default=os.environ.get("MORISHIO_MANUAL_DAY", ""))
    parser.add_argument("--output-dir", default=os.environ.get("MORISHIO_OUTPUT_DIR", "generated/morishio"))
    return parser.parse_args()


def resolve_day(start_date: str, manual_day: str) -> int:
    manual_day = str(manual_day or "").strip()
    if manual_day:
        day = int(manual_day)
    else:
        day = (datetime.now().date() - date.fromisoformat(start_date)).days + 1
    return max(1, min(30, day))


def font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
    ]
    for path in candidates:
        try:
            if Path(path).exists():
                return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def wrap_text(text: str, max_chars: int) -> str:
    lines = []
    for raw in str(text).split("\n"):
        raw = raw.strip()
        if not raw:
            lines.append("")
            continue
        while raw:
            lines.append(raw[:max_chars])
            raw = raw[max_chars:]
    return "\n".join(lines)


def draw_wrapped(draw, xy, text: str, fnt, fill=(20, 20, 20), max_chars=16, spacing=8):
    x, y = xy
    for line in wrap_text(text, max_chars).split("\n"):
        draw.text((x, y), line, font=fnt, fill=fill)
        y += getattr(fnt, "size", 24) + spacing
    return y


def post_title(day: int, index: int) -> str:
    roles = ["フック", "日常の違和感", "手がかり", "危険接近", "明日への引き"]
    return f"{DAY_TITLES[day - 1]}：{roles[index - 1]}"


def panel_lines(day: int, index: int) -> List[str]:
    base = ARC_LINES[day - 1]
    return [
        f"状況提示：{post_title(day, index)}",
        "Aたくやが最初の違和感を見る",
        "Bもとやが記録と法則を読む",
        "Cかえてが声や記憶に反応する",
        "Dばやしが動き、危険が近づく",
        f"引き：{base}" if index < 5 else f"強い引き：{base} 続きは明日9:00。",
    ]


def make_prompt(day: int, index: int) -> str:
    panels = "\n".join(f"{i+1}. {line}" for i, line in enumerate(panel_lines(day, index)))
    return f"""Instagram vertical monochrome horror manga page, 6 panels.
Series: 『{SERIES}』
Order label: DAY{day:02d} | {index}/5
Cast: {CAST}
Theme: a modern apartment horror about morishio salt piles, a mailbox, thin paper slips, unseen presence inside a room, and a house that chooses its next resident.
Day title: {DAY_TITLES[day - 1]}
Post title: {post_title(day, index)}
Panel plan:
{panels}
Style: black-and-white Japanese web horror manga, readable panels, suspenseful but not graphic, no KRUMP/dance elements. The 5th image must end on the strongest cliffhanger.
"""


def make_image(path: Path, day: int, index: int, question: str):
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), (247, 247, 244))
    draw = ImageDraw.Draw(img)
    f_big, f_mid, f_text, f_small = font(48, True), font(31, True), font(27), font(22)

    draw.rectangle((0, 0, W, 150), fill=(18, 18, 18))
    draw.text((40, 24), f"DAY{day:02d} | {index}/5", font=f_mid, fill=(255, 255, 255))
    draw.text((40, 78), f"『{SERIES}』 {DAY_TITLES[day - 1]}", font=f_small, fill=(235, 235, 235))
    draw.text((790, 32), f"{index}/5", font=f_big, fill=(255, 255, 255))
    draw_wrapped(draw, (40, 170), post_title(day, index), f_big, max_chars=18)
    draw.text((40, 230), "1枚6コマ / 投稿順番号入り", font=f_small, fill=(80, 80, 80))

    margin, top, gap = 40, 285, 24
    pw = (W - margin * 2 - gap) // 2
    ph = 430
    symbols = ["○", "□", "△", "||||", "▣", "／"]
    for n, text in enumerate(panel_lines(day, index), start=1):
        row, col = divmod(n - 1, 2)
        x1 = margin + col * (pw + gap)
        y1 = top + row * (ph + gap)
        x2, y2 = x1 + pw, y1 + ph
        draw.rectangle((x1, y1, x2, y2), fill=(255, 255, 255) if n < 6 else (230, 230, 226), outline=(20, 20, 20), width=4)
        draw.rectangle((x1, y1, x1 + 58, y1 + 46), fill=(20, 20, 20))
        draw.text((x1 + 17, y1 + 7), str(n), font=f_mid, fill=(255, 255, 255))
        draw.text((x1 + 310, y1 + 72), symbols[n - 1], font=font(78, True), fill=(60, 60, 60))
        draw_wrapped(draw, (x1 + 22, y1 + 270), text, f_text, max_chars=15)

    footer_y = 1680
    draw.rectangle((0, footer_y, W, H), fill=(18, 18, 18))
    draw.text((40, footer_y + 34), "5枚目で必ず引き。違和感をコメントへ。", font=f_mid, fill=(255, 255, 255))
    draw_wrapped(draw, (40, footer_y + 92), question, f_text, fill=(235, 235, 235), max_chars=24)
    draw.text((40, footer_y + 150), "続きは明日9:00", font=f_mid, fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def make_caption(day: int, question: str) -> str:
    return f"""【DAY{day:02d}｜{SERIES}】
{DAY_TITLES[day - 1]}

{ARC_LINES[day - 1]}

盛り塩を崩した日から、玄関・郵便受け・壁の向こうで、少しずつ“家”が変わっていく。
今日の5枚目に、明日の異変の手がかりがあります。

{question}
考察はコメントへ。
続きは明日9:00。

#ホラー漫画 #創作漫画 #怖い話 #洒落怖風 #漫画連載 #盛り塩の家 #インスタ漫画 #都市伝説
"""


def main():
    args = parse_args()
    day = resolve_day(args.start_date, args.manual_day)
    question = "5枚目の違和感、どこだと思う？"
    day_dir = Path(args.output_dir) / f"DAY{day:02d}"
    day_dir.mkdir(parents=True, exist_ok=True)

    posts = []
    for index in range(1, 6):
        img_name = f"DAY{day:02d}_{index}of5.png"
        prompt_name = f"DAY{day:02d}_{index}of5_prompt.txt"
        make_image(day_dir / img_name, day, index, question)
        (day_dir / prompt_name).write_text(make_prompt(day, index), encoding="utf-8")
        posts.append({
            "order_label": f"DAY{day:02d} | {index}/5",
            "image_file": img_name,
            "prompt_file": prompt_name,
            "title": post_title(day, index),
            "panels": panel_lines(day, index),
        })

    caption_name = f"DAY{day:02d}_caption.txt"
    (day_dir / caption_name).write_text(make_caption(day, question), encoding="utf-8")
    package = {
        "series_title": SERIES,
        "day": day,
        "day_title": DAY_TITLES[day - 1],
        "schedule": "09:00 Asia/Tokyo daily",
        "image_count": 5,
        "panels_per_image": 6,
        "numbering_rule": "DAYxx | x/5",
        "caption_file": caption_name,
        "posts": posts,
    }
    (day_dir / f"DAY{day:02d}_post_package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {SERIES} DAY{day:02d} at {day_dir}")
    for p in posts:
        print(f"- {p['image_file']} ({p['order_label']})")


if __name__ == "__main__":
    main()
