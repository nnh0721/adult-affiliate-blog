#!/usr/bin/env python3
"""投稿文ジェネレータ（半自動）。標準ライブラリのみ。

CSVの作品情報から、テンプレートの投稿文の下書きを作る。投稿・リンク作成・画像添付は人が行う。
  同人（セール型）: python3 tools/make_post.py doujin data/doujin_sale_2026-10-08.csv --today 2026-10-09
  動画（ランキング型）: python3 tools/make_post.py av data/av_weekly_2026-10-08.csv --asof 2026-10-08

ルール（参加規約・ガイドラインに基づく）:
- status が ng の作品は出さない。review は「要確認」つきで出す。ok だけ警告なし。
- 感想(comment)は watched=1 のときだけ使う。観ていない作品の感想は出さない（虚偽レビュー防止）。
- 先頭に【PR】。リンクは {LINK} の位置に人が貼る。
- 断定的な表現（最高・絶対・必ず・日本一・No.1・最安・ホンモノなど）が感想に含まれたら警告。
- 長さはXの重み付け（全角=2、半角=1、URL=23、上限280）で概算。
"""
import argparse, csv, datetime as dt, sys, os

BANNED = ["最高", "最強", "絶対", "必ず", "日本一", "No.1", "NO.1", "最安", "ホンモノ", "間違いない",
          "ガチで抜ける", "JK", "無理やり", "強制", "調教", "奴隷"]
LINK_WEIGHT = 23


def weight(text: str) -> int:
    t = text.replace("{LINK}", "")
    w = LINK_WEIGHT
    for ch in t:
        w += 1 if ord(ch) < 0x80 else 2
    return w


def md(d: dt.date) -> str:
    return f"{d.month}/{d.day}"


def comment_of(row, warns):
    c = (row.get("comment") or "").strip()
    if not c:
        return ""
    if (row.get("watched") or "").strip() != "1":
        warns.append("comment があるが watched=1 でないため、感想は出力しません（観た作品だけに感想を書く）")
        return ""
    bad = [b for b in BANNED if b in c]
    if bad:
        warns.append("感想に断定的な語句があります: " + "、".join(bad))
    return f"一言：{c}"


def doujin_post(row, today, warns):
    end = dt.date.fromisoformat(row["sale_end"])
    left = (end - today).days
    if left < 0:
        return None
    head = "⏳本日まで" if left == 0 else f"⏳あと{left}日"
    if row.get("end_approx") == "1":
        warns.append("終了日は「残り◯日」からの推定です。販売ページで確認してから投稿")
    lines = [
        f"【PR】{head}｜{row['discount_pct']}%OFF",
        f"『{row['title']}』／{row['creator']}",
        f"{int(row['price_now']):,}円（元{int(row['price_orig']):,}円）・{md(end)}まで（{md(today)}時点）",
    ]
    c = comment_of(row, warns)
    if c:
        lines.append(c)
    lines.append("{LINK}")
    return "\n".join(lines)


def av_post(row, asof, warns):
    lines = [
        f"【PR】週間{row['rank']}位｜お気に入り{int(row['fav']):,}人",
        f"『{row['title']}』／{row['performer']}",
        f"{int(row['price_from']):,}円〜（{md(asof)}時点）",
    ]
    c = comment_of(row, warns)
    if c:
        lines.append(c)
    lines.append("{LINK}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["doujin", "av"])
    ap.add_argument("csv")
    ap.add_argument("--today", default=dt.date.today().isoformat(), help="投稿日（同人: 残り日数の計算に使用）")
    ap.add_argument("--asof", default=None, help="av: ランキング取得日（既定は today）")
    ap.add_argument("--out", default=None, help="出力先ファイル（省略時は標準出力）")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.today)
    asof = dt.date.fromisoformat(a.asof) if a.asof else today

    rows = list(csv.DictReader(open(a.csv, encoding="utf-8")))
    out, skipped, expired = [], [], []
    for r in rows:
        st = (r.get("status") or "").strip()
        if st == "ng":
            skipped.append(f"{r['rank']}位 {r['title'][:24]}…（{r.get('reason','')}）")
            continue
        warns = []
        body = doujin_post(r, today, warns) if a.kind == "doujin" else av_post(r, asof, warns)
        if body is None:
            expired.append(f"{r['rank']}位 {r['title'][:24]}…（セール終了）")
            continue
        w = weight(body)
        if w > 280:
            warns.append(f"長さが重み付けで {w} (>280)。短くしてください")
        if st == "review":
            warns.insert(0, "要確認: " + (r.get("reason") or "パッケージ・題名を確認") + "。確認前は投稿しない")
        out.append((r, body, w, warns))

    lines = [f"# 投稿文の下書き（{a.kind}）", f"- 生成日: {dt.date.today().isoformat()} / 基準日: {today.isoformat()}"
             + (f" / ランキング取得日: {asof.isoformat()}" if a.kind == "av" else ""),
             f"- 入力: {a.csv}",
             "- 投稿前チェック: ①パッケージ・題名がガイドライン（暴力・強要・未成年連想・近親）に反しないか ②価格・順位・期限を販売ページで再確認 "
             "③画像は商品メイン画像かサンプル画像（拡大・縮小のみ） ④リンクは自分のアフィリエイトリンク ⑤感想は観た作品だけ", ""]
    for r, body, w, warns in sorted(out, key=lambda x: (x[0].get("sale_end", ""), int(x[0]["rank"]))):
        lines.append(f"## {r['rank']}位 {r['title'][:40]}  （{r.get('status')}）")
        for x in warns:
            lines.append(f"- ⚠ {x}")
        lines.append(f"- 長さの目安: {w}/280")
        lines.append("```")
        lines.append(body)
        lines.append("```")
        lines.append("")
    if skipped:
        lines.append("## 紹介しない作品（status=ng）")
        lines += [f"- {s}" for s in skipped]
        lines.append("")
    if expired:
        lines.append("## 終了済み")
        lines += [f"- {s}" for s in expired]
    text = "\n".join(lines)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        open(a.out, "w", encoding="utf-8").write(text)
        print(f"wrote {a.out}: {len(out)} drafts, {len(skipped)} ng, {len(expired)} expired")
    else:
        print(text)


if __name__ == "__main__":
    main()
