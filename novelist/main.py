"""CLI 入口 — Novelist 命令行工具"""

import click
from novelist.agents import SearchAgent, WriterAgent
from novelist.graph import run_novel_workflow


@click.group()
def cli():
    """Novelist — AI 小说搜索、阅读与创作平台"""
    pass


# ═══════════════════════════════════════════
# 搜索
# ═══════════════════════════════════════════

@cli.command()
@click.argument("query")
@click.option("-n", "--num", default=8, help="返回结果数量（默认 8）")
def search(query: str, num: int):
    """联网搜索小说。示例: novelist search '开局满级的无敌文'"""
    agent = SearchAgent()
    click.echo(f"\n🔍 正在搜索: {query}\n")

    results = agent.search(query, max_results=num)

    if not results:
        click.echo("未找到相关结果。")
        return

    for i, r in enumerate(results, 1):
        click.echo(f"{i}. {r['title']}")
        click.echo(f"   {r['url']}")
        click.echo(f"   {r['snippet'][:120]}...")
        click.echo()


# ═══════════════════════════════════════════
# 短篇小说（Phase 1 保留）
# ═══════════════════════════════════════════

@cli.command(name="write-short")
@click.option("--genre", "-g", default="", help="题材（玄幻、都市、科幻等）")
@click.option("--theme", "-t", default="", help="主题")
@click.option("--style", "-s", default="", help="写作风格")
@click.option("--protagonist", "-p", default="", help="主角设定")
@click.option("--length", "-l", type=int, default=1500, help="字数（默认 1500）")
@click.option("--extra", "-e", default="", help="额外要求")
def write_short(genre, theme, style, protagonist, length, extra):
    """AI 创作短篇小说（单 Agent 快速生成）"""
    agent = WriterAgent()

    click.echo("\n✍️  正在创作短篇...\n")
    click.echo("─" * 50)

    content = agent.write(
        genre=genre, theme=theme, style=style,
        protagonist=protagonist, length=length, extra=extra,
    )

    click.echo(content)
    click.echo("─" * 50)

    filepath = agent.save(content, title=theme or genre or "小说")
    click.echo(f"\n✅ 已保存至: {filepath}")


# ═══════════════════════════════════════════
# 长篇小说（Phase 2：多 Agent 协作）
# ═══════════════════════════════════════════

@cli.command(name="write")
@click.option("--genre", "-g", default="", help="题材（玄幻、都市、科幻等）")
@click.option("--theme", "-t", default="", help="主题（逆天改命、星际殖民等）")
@click.option("--style", "-s", default="", help="写作风格（热血、轻松、悬疑等）")
@click.option("--protagonist", "-p", default="", help="主角设定（姓名、性格等）")
@click.option("--chapters", "-c", type=int, default=5, help="章节数（默认 5）")
@click.option("--words", "-w", type=int, default=1000, help="每章字数（默认 1000）")
@click.option("--extra", "-e", default="", help="额外要求")
def write_novel(genre, theme, style, protagonist, chapters, words, extra):
    """
    AI 创作长篇小说（多 Agent 协作模式）。

    流程：规划 → 角色设计 → 大纲 → 逐章写作+审核 → 完整小说

    示例:
        novelist write -g 玄幻 -t '逆天改命' -c 10 -w 2000
    """
    click.echo("\n" + "=" * 60)
    click.echo("  Novelist 多 Agent 写作模式")
    click.echo("=" * 60)
    click.echo(f"  题材: {genre or '不限'} | 主题: {theme or '不限'} | 风格: {style or '默认'}")
    click.echo(f"  章节: {chapters}章 × {words}字 | 主角: {protagonist or '自动设定'}")
    click.echo("=" * 60)

    # 运行多 Agent 工作流
    result = run_novel_workflow(
        genre=genre,
        theme=theme,
        style=style,
        protagonist=protagonist,
        chapters=chapters,
        words_per_chapter=words,
        extra=extra,
    )

    # 输出结果
    click.echo("\n" + "=" * 60)
    click.echo("  🎉 小说创作完成！")
    click.echo("=" * 60)
    click.echo(f"  标题: {result['plan'].get('title', '未命名')}")
    click.echo(f"  已完成: {result['current_chapter']} 章")
    click.echo(f"  数据库 ID: {result['novel_id']}")

    # 编译完整小说保存到文件
    from novelist.tools import db_get_all_chapters, write_file, db_get_novel
    from datetime import datetime

    novel_info = db_get_novel(result["novel_id"])
    chapters_data = db_get_all_chapters(result["novel_id"])

    # 生成 Markdown 格式
    lines = [
        f"# {result['plan'].get('title', '未命名')}",
        "",
        f"> 题材：{genre} | 主题：{theme} | 风格：{style}",
        f"> 由 Novelist AI 多 Agent 协作创作",
        "",
    ]

    for ch in chapters_data:
        lines.append(f"## 第{ch['number']}章 {ch['title']}")
        lines.append("")
        lines.append(ch["content"])
        lines.append("")
        lines.append("---")
        lines.append("")

    full_text = "\n".join(lines)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = result["plan"].get("title", "小说")
    filename = f"{date_str}_{title}.md"
    filepath = write_file(f"output/{filename}", full_text)
    click.echo(f"  📄 已保存至: {filepath}")

    # 显示各章摘要
    click.echo("\n  📋 章节摘要:")
    for ch in chapters_data:
        click.echo(f"    第{ch['number']}章: {ch['title']} ({ch['word_count']}字)")

    # 自动建立向量索引（用于后续 RAG 检索）
    click.echo("\n  🔧 正在建立向量索引...")
    try:
        from novelist.memory import add_all_chapters
        count = add_all_chapters(result["novel_id"])
        click.echo(f"  ✅ 向量索引建立完成（{count} 章）")
    except Exception as e:
        click.echo(f"  ⚠️  向量索引失败（不影响使用）: {e}")


# ═══════════════════════════════════════════
# 修改章节（Phase 3）
# ═══════════════════════════════════════════

@cli.command()
@click.argument("novel_id", type=int)
@click.argument("chapter_no", type=int)
@click.argument("feedback")
def edit(novel_id: int, chapter_no: int, feedback: str):
    """
    修改小说章节。\n
    示例: novelist edit 1 3 "打斗不够精彩，加一个反转"
    """
    from novelist.tools import db_get_chapter, db_save_chapter, db_get_novel
    from novelist.agents import EditorAgent

    # 获取原章节
    chapter = db_get_chapter(novel_id, chapter_no)
    if not chapter:
        click.echo(f"❌ 未找到小说 {novel_id} 的第 {chapter_no} 章")
        return

    novel = db_get_novel(novel_id)

    click.echo(f"\n✏️  正在修改《{novel.get('title', '')}》第 {chapter_no} 章...")
    click.echo(f"📝 修改意见: {feedback}\n")

    # 执行修改
    editor = EditorAgent()
    new_content = editor.edit_chapter(
        original_content=chapter["content"],
        user_feedback=feedback,
        novel_id=novel_id,
        chapter_no=chapter_no,
    )

    # 保存
    db_save_chapter(
        novel_id=novel_id,
        volume=chapter.get("volume", 1),
        number=chapter_no,
        title=chapter["title"],
        summary=chapter.get("summary", ""),
        content=new_content,
    )

    click.echo("─" * 50)
    click.echo(new_content[:500] + ("..." if len(new_content) > 500 else ""))
    click.echo("─" * 50)
    click.echo(f"\n✅ 第 {chapter_no} 章已修改并保存（原{chapter['word_count']}字 → 新{len(new_content)}字）")

    # 更新向量索引
    click.echo("🔧 正在更新向量索引...")
    try:
        from novelist.memory import add_chapter
        add_chapter(novel_id, chapter_no, chapter["title"], new_content)
        click.echo("✅ 向量索引更新完成")
    except Exception as e:
        click.echo(f"⚠️  向量索引更新失败: {e}")


# ═══════════════════════════════════════════
# 导入小说（Phase 5）
# ═══════════════════════════════════════════

@cli.command()
@click.argument("url")
def import_novel(url: str):
    """
    从网页导入小说。\n
    示例: novelist import-novel https://example.com/novel/chapter1.html
    """
    from novelist.agents import ImportAgent

    click.echo(f"\n📥 正在导入: {url}\n")

    try:
        agent = ImportAgent()
        result = agent.import_from_url(url)
        click.echo(f"✅ 导入成功！")
        click.echo(f"   标题: {result.get('title', '未知')}")
        click.echo(f"   作者: {result.get('author', '未知')}")
        if result.get("chapter_count"):
            click.echo(f"   章节: {result['chapter_count']}章 ({result.get('word_count', 0)}字)")
        if result.get("description"):
            click.echo(f"   简介: {result['description'][:100]}...")
        if result.get("warning"):
            click.echo(f"   ⚠️  {result['warning']}")
        click.echo(f"   ID: {result['novel_id']}")
    except Exception as e:
        click.echo(f"❌ 导入失败: {e}")


if __name__ == "__main__":
    cli()
