#!/usr/bin/env python3
"""
そなえLAB - 週次記事自動生成スクリプト
毎週1記事をGemini APIで生成し、GitHub Pagesサイトに追加する

使い方:
  python scripts/generate_post.py                  # 通常実行（次のtopicを生成）
  python scripts/generate_post.py --topic 3        # topics.jsonのindex指定
  python scripts/generate_post.py --dry-run        # 生成内容を表示のみ（ファイル保存なし）
"""

import argparse
import json
import os
import re
import sys
import textwrap
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Gemini API
try:
    import google.generativeai as genai
except ImportError:
    print("Error: google-generativeai が未インストールです。")
    print("  pip install google-generativeai")
    sys.exit(1)

# ── パス設定 ──────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT   = SCRIPT_DIR.parent
POSTS_DIR   = REPO_ROOT / "posts"
IMAGES_DIR  = REPO_ROOT / "images"
TOPICS_FILE = SCRIPT_DIR / "topics.json"

AMAZON_TAG     = "msalpha0123-22"
GEMINI_MODEL   = "gemini-2.0-flash"
JST            = timezone(timedelta(hours=9))


# ── ユーティリティ ─────────────────────────────
def load_topics() -> list:
    with open(TOPICS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_topics(topics: list) -> None:
    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)


def get_next_pending(topics: list) -> tuple[int, dict | None]:
    for i, t in enumerate(topics):
        if t.get("status") != "published":
            return i, t
    return -1, None


def load_posts_json() -> list:
    path = POSTS_DIR / "posts.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_posts_json(posts: list) -> None:
    with open(POSTS_DIR / "posts.json", "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


# ── SVGカバー画像生成 ──────────────────────────
CATEGORY_THEMES = {
    "防災グッズ":   {"bg1": "#1d4e3e", "bg2": "#2d7a5f", "emoji": "🎒", "label_color": "#a8e6cf"},
    "非常食・備蓄": {"bg1": "#7f4e1d", "bg2": "#b5722a", "emoji": "🍱", "label_color": "#f9d9a8"},
    "電源・エネルギー": {"bg1": "#1a3a6e", "bg2": "#2656a8", "emoji": "⚡", "label_color": "#aac8f5"},
    "衛生・医療":   {"bg1": "#005c4b", "bg2": "#008c72", "emoji": "🧼", "label_color": "#b2f0e4"},
    "防犯":         {"bg1": "#3a1a5c", "bg2": "#6032a0", "emoji": "🔒", "label_color": "#d8b8f8"},
    "便利グッズ":   {"bg1": "#5c1a3a", "bg2": "#a03060", "emoji": "✨", "label_color": "#f8b8d8"},
}


def wrap_text_svg(text: str, max_chars: int = 16) -> list[str]:
    """日本語テキストをSVG用に折り返す"""
    lines = []
    while len(text) > max_chars:
        lines.append(text[:max_chars])
        text = text[max_chars:]
    if text:
        lines.append(text)
    return lines[:3]  # 最大3行


def generate_svg_cover(topic: dict, slug: str) -> str:
    cat = topic.get("category", "防災グッズ")
    theme = CATEGORY_THEMES.get(cat, CATEGORY_THEMES["防災グッズ"])

    # タイトルを短くする（ ── 以降を除く）
    title = topic["title"].split("──")[0].split("—")[0].strip()
    if len(title) > 20:
        title = title[:20] + "…"

    lines = wrap_text_svg(title, 14)
    text_y_start = 140 - (len(lines) - 1) * 20

    text_lines_svg = ""
    for i, line in enumerate(lines):
        y = text_y_start + i * 36
        text_lines_svg += f'<text x="240" y="{y}" text-anchor="middle" font-size="26" font-weight="bold" fill="white" font-family="sans-serif">{line}</text>\n'

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="480" height="280" viewBox="0 0 480 280">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{theme['bg1']}"/>
      <stop offset="100%" stop-color="{theme['bg2']}"/>
    </linearGradient>
    <filter id="shadow">
      <feDropShadow dx="0" dy="2" stdDeviation="4" flood-opacity="0.3"/>
    </filter>
  </defs>

  <!-- 背景 -->
  <rect width="480" height="280" fill="url(#bg)"/>

  <!-- 装飾サークル -->
  <circle cx="400" cy="40" r="80" fill="white" opacity="0.05"/>
  <circle cx="60" cy="240" r="60" fill="white" opacity="0.05"/>
  <circle cx="440" cy="220" r="40" fill="white" opacity="0.04"/>

  <!-- ドット柄 -->
  <pattern id="dots" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
    <circle cx="10" cy="10" r="1.5" fill="white" opacity="0.08"/>
  </pattern>
  <rect width="480" height="280" fill="url(#dots)"/>

  <!-- カテゴリバッジ -->
  <rect x="20" y="20" width="120" height="30" rx="15" fill="white" opacity="0.15"/>
  <text x="80" y="40" text-anchor="middle" font-size="13" fill="{theme['label_color']}" font-family="sans-serif" font-weight="bold">{cat}</text>

  <!-- 絵文字アイコン -->
  <text x="240" y="100" text-anchor="middle" font-size="52" filter="url(#shadow)">{theme['emoji']}</text>

  <!-- タイトルテキスト -->
  {text_lines_svg}

  <!-- サイト名 -->
  <rect x="0" y="248" width="480" height="32" fill="black" opacity="0.3"/>
  <text x="240" y="269" text-anchor="middle" font-size="14" fill="white" opacity="0.9" font-family="sans-serif" font-weight="bold">そなえLAB</text>
</svg>"""

    return svg


# ── Gemini API で記事生成 ──────────────────────
ARTICLE_PROMPT_TEMPLATE = """
あなたは「そなえLAB」という防災・便利グッズ実体験レビューブログの記者です。
読者は30〜50代の子育て世代または一人暮らし世代で、防災には関心があるけど「完璧には揃えられていない」という等身大の悩みを持っています。

以下のテーマで記事を書いてください：

【テーマ】
タイトル案: {title}
カテゴリ: {category}
対象読者: {target_audience}

【含めるべき内容（参考）】
{key_points}

【紹介する商品・リンク】
記事の末尾、または自然な流れで以下のアフィリエイトリンクを挿入してください。
{products_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【文体ルール】
・一人称は「私」「わが家」
・断定を避ける（「〜かもしれません」「〜と思います」「〜な気がします」）
・語り口を親しみやすく（「〜なんです」「〜ですよね」「〜かな、と」）
・具体的な体験・数値を交える（「実際にやってみたら」「計算してみると」）
・完璧主義を押し付けない（「まずひとつだけでも」「できる範囲から」）
・失敗談・正直な感想を含める（「使ったことがなかった」「思ったより…」）
・上から目線にならない
・「絶対」「必ず」などの断定的強調表現は避ける

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【出力フォーマット（Markdownのみ。コードブロックは使わない）】

記事の冒頭（h2より前）に以下を入れてください：
> ※ この記事には商品へのアフィリエイトリンクが含まれます。リンクから購入いただくと、サイト運営の支援になります。

本文（1500〜2500文字）を h2・h3 を使って構成してください。
h1 は使わないでください（タイトルはシステムが別途表示します）。

本文中に、以下の形式でアフィリエイトリンクを1〜2箇所自然に埋め込んでください：

<a class="affiliate-box" href="{url}" target="_blank" rel="nofollow sponsored noopener">
商品カテゴリの説明テキスト（例：Amazonで防災ラジオを探してみる）
</a>

記事の末尾は「## おわりに」で締めてください。
次回予告は書かなくて構いません。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


def build_products_text(products: list) -> str:
    if not products:
        return "（商品紹介なし）"
    lines = []
    for p in products:
        lines.append(f"- 商品名: {p['title']}")
        lines.append(f"  リンク: {p['url']}")
    return "\n".join(lines)


def generate_article(topic: dict, model) -> str:
    """Gemini APIで記事を生成する（リトライあり）"""
    products = topic.get("products", [])
    first_url = products[0]["url"] if products else f"https://www.amazon.co.jp/s?k={topic['slug_base']}&tag={AMAZON_TAG}"

    prompt = ARTICLE_PROMPT_TEMPLATE.format(
        title=topic["title"],
        category=topic.get("category", "防災グッズ"),
        target_audience=topic.get("target_audience", "防災に関心のある家庭"),
        key_points="\n".join(f"- {p}" for p in topic.get("key_points", [])),
        products_text=build_products_text(products),
        url=first_url,
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.8,
                    "max_output_tokens": 4096,
                }
            )
            return response.text
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower():
                wait = 60 * (attempt + 1)
                print(f"  レート制限: {wait}秒待機してリトライ ({attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                if attempt == max_retries - 1:
                    raise
                wait = 10 * (attempt + 1)
                print(f"  エラー（{e}）: {wait}秒後にリトライ ({attempt+1}/{max_retries})")
                time.sleep(wait)

    raise RuntimeError("記事生成に失敗しました（リトライ上限）")


# ── メイン処理 ─────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="そなえLAB 週次記事生成スクリプト")
    parser.add_argument("--topic", type=int, default=None, help="topics.jsonのインデックス（未指定=次のpending）")
    parser.add_argument("--dry-run", action="store_true", help="ファイルを保存せず、生成結果を表示のみ")
    args = parser.parse_args()

    # Gemini API キーの確認
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: 環境変数 GEMINI_API_KEY が設定されていません")
        sys.exit(1)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    # トピック読み込み
    topics = load_topics()

    if args.topic is not None:
        idx = args.topic
        if idx < 0 or idx >= len(topics):
            print(f"Error: --topic {idx} は範囲外です（0〜{len(topics)-1}）")
            sys.exit(1)
        topic = topics[idx]
    else:
        idx, topic = get_next_pending(topics)
        if topic is None:
            print("ℹ️  すべてのトピックが公開済みです。topics.jsonに新しいトピックを追加してください。")
            sys.exit(0)

    print(f"\n{'='*60}")
    print(f"📝 生成対象トピック [{idx}]:")
    print(f"   タイトル : {topic['title']}")
    print(f"   カテゴリ : {topic.get('category', '未設定')}")
    print(f"   予定日   : {topic.get('scheduled_date', '未設定')}")
    print(f"{'='*60}\n")

    # 日付の決定
    today = datetime.now(JST)
    # scheduled_date がある場合は参考にするが、実際には今日の日付を使用
    pub_date = today.strftime("%Y-%m-%d")

    slug = f"{pub_date}-{topic['slug_base']}"

    print("🤖 Gemini APIで記事を生成中...")
    md_content = generate_article(topic, model)
    print(f"   ✅ 記事生成完了（{len(md_content)}文字）")

    print("🎨 SVGカバー画像を生成中...")
    svg_content = generate_svg_cover(topic, slug)
    print("   ✅ SVG生成完了")

    # posts.jsonに追加するメタデータ
    post_meta = {
        "slug": slug,
        "title": topic["title"],
        "date": pub_date,
        "summary": topic.get("key_points", [""])[0] if topic.get("key_points") else "",
        "cover": f"images/{topic['slug_base']}-cover.svg",
        "category": topic.get("category", "防災グッズ"),
        "products": topic.get("products", []),
        "recommend": len(topic.get("products", [])) > 0
    }

    if args.dry_run:
        print("\n" + "="*60)
        print("📄 DRY RUN - 生成された記事（最初の1000文字）:")
        print("="*60)
        print(md_content[:1000] + ("..." if len(md_content) > 1000 else ""))
        print("\n" + "="*60)
        print("📋 posts.jsonに追加される情報:")
        print(json.dumps(post_meta, ensure_ascii=False, indent=2))
        print("="*60)
        print("\n✅ DRY RUNモードのため、ファイルは保存されませんでした。")
        return

    # ファイル保存
    print("\n💾 ファイルを保存中...")

    # 記事MarkDownを保存
    md_path = POSTS_DIR / f"{slug}.md"
    md_path.write_text(md_content, encoding="utf-8")
    print(f"   ✅ {md_path}")

    # SVGカバーを保存
    svg_path = IMAGES_DIR / f"{topic['slug_base']}-cover.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    print(f"   ✅ {svg_path}")

    # posts.jsonを更新
    posts = load_posts_json()
    # 同じslugが既にあれば更新、なければ追加
    existing_idx = next((i for i, p in enumerate(posts) if p["slug"] == slug), None)
    if existing_idx is not None:
        posts[existing_idx] = post_meta
        print(f"   ✅ posts.json 更新（既存スラッグ）")
    else:
        posts.insert(0, post_meta)
        print(f"   ✅ posts.json 追加（新規）")
    save_posts_json(posts)

    # topicsのstatusをpublishedに更新
    topics[idx]["status"] = "published"
    topics[idx]["published_date"] = pub_date
    save_topics(topics)
    print(f"   ✅ topics.json 更新（status=published）")

    print(f"\n🎉 完了！記事が追加されました: {slug}")
    print(f"   URL: https://bousai-blog.github.io/post.html?slug={slug}")


if __name__ == "__main__":
    main()
