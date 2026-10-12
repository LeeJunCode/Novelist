"""Agent 工具集 — 网络搜索、文件读写、数据库操作"""

import json
from pathlib import Path

from novelist.models import get_session, Novel, Character, Chapter


# ═══════════════════════════════════════════
# 网络搜索
# ═══════════════════════════════════════════

def web_search(query: str, max_results: int = 10, timeout: int = 10) -> list[dict]:
    """网络搜索，优先 DuckDuckGo，失败时回退到 Bing 直接搜索。"""
    # 先试 ddgs（可能超时）
    try:
        from ddgs import DDGS
        results = []
        with DDGS(timeout=timeout) as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        if results:
            return results
    except Exception:
        pass

    # 回退：直接请求 cn.bing.com
    return _bing_search(query, max_results, timeout)


def fetch_page(url: str, timeout: int = 15) -> str:
    """抓取网页 HTML 内容"""
    import httpx
    resp = httpx.get(
        url, timeout=timeout,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def _bing_search(query: str, max_results: int = 10, timeout: int = 10) -> list[dict]:
    """直接请求 cn.bing.com 搜索，解析 HTML 提取结果"""
    import re
    import httpx

    try:
        resp = httpx.get(
            "https://cn.bing.com/search",
            params={"q": query, "count": max_results},
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        if resp.status_code != 200:
            return []

        html = resp.text
        results = []

        # 用 h2 标签定位每个搜索结果
        h2_blocks = re.split(r'<h2[^>]*>', html)[1:]  # 第一个 split 片段是 h2 之前的内容，丢弃

        for block in h2_blocks[:max_results]:
            # 提取标题和链接
            title_m = re.search(r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not title_m:
                continue
            url = title_m.group(1)
            title = re.sub(r'<[^>]+>', '', title_m.group(2)).strip()

            # 提取摘要（h2 之后最近的 p 标签内容）
            snippet_m = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
            if snippet_m:
                snippet = re.sub(r'<[^>]+>', '', snippet_m.group(1)).strip()
                # 清理 HTML 实体
                snippet = snippet.replace("&ensp;", " ").replace("&#0183;", "·")
            else:
                snippet = ""

            results.append({"title": title, "url": url, "snippet": snippet})

        return results
    except Exception:
        return []


# ═══════════════════════════════════════════
# 文件读写
# ═══════════════════════════════════════════

def read_file(filepath: str | Path) -> str:
    """读取文件内容"""
    return Path(filepath).read_text(encoding="utf-8")


def write_file(filepath: str | Path, content: str) -> str:
    """写入文件（自动创建父目录），返回文件路径"""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


# ═══════════════════════════════════════════
# 数据库操作（Phase 2+）
# ═══════════════════════════════════════════

def db_create_novel(title: str, genre: str = "", theme: str = "", style: str = "") -> int:
    """创建新小说记录，返回 novel_id"""
    with get_session() as session:
        novel = Novel(title=title, genre=genre, theme=theme, style=style, status="planning")
        session.add(novel)
        session.commit()
        return novel.id


def db_update_novel(novel_id: int, **kwargs) -> None:
    """更新小说信息"""
    with get_session() as session:
        novel = session.get(Novel, novel_id)
        if novel:
            for k, v in kwargs.items():
                if hasattr(novel, k):
                    setattr(novel, k, v)
            session.commit()


def db_get_novel(novel_id: int) -> dict:
    """获取小说完整信息（含角色和章节列表）"""
    with get_session() as session:
        novel = session.get(Novel, novel_id)
        if not novel:
            return {}
        return {
            "id": novel.id,
            "title": novel.title,
            "genre": novel.genre,
            "theme": novel.theme,
            "style": novel.style,
            "status": novel.status,
            "characters": [
                {"name": c.name, "role_type": c.role_type, "personality": c.personality,
                 "background": c.background, "abilities": c.abilities}
                for c in novel.characters
            ],
            "chapter_count": len(novel.chapters),
        }


def db_save_characters(novel_id: int, characters: list[dict]) -> int:
    """批量保存角色，返回保存数量"""
    with get_session() as session:
        # 先清除旧角色
        session.query(Character).filter(Character.novel_id == novel_id).delete()
        for c in characters:
            session.add(Character(
                novel_id=novel_id,
                name=c.get("name", ""),
                role_type=c.get("role_type", "supporting"),
                personality=c.get("personality", ""),
                background=c.get("background", ""),
                abilities=c.get("abilities", ""),
                appearance=c.get("appearance", ""),
                relationships=c.get("relationships", ""),
            ))
        session.commit()
        return len(characters)


def db_query_characters(novel_id: int, name: str = "") -> list[dict]:
    """查询小说角色，可指定角色名模糊搜索"""
    with get_session() as session:
        query = session.query(Character).filter(Character.novel_id == novel_id)
        if name:
            query = query.filter(Character.name.contains(name))
        return [
            {"name": c.name, "role_type": c.role_type, "personality": c.personality,
             "background": c.background, "abilities": c.abilities, "appearance": c.appearance}
            for c in query.all()
        ]


def db_save_chapter(novel_id: int, volume: int, number: int, title: str,
                    summary: str = "", content: str = "") -> int:
    """保存/更新章节，返回 chapter_id"""
    with get_session() as session:
        # 查找是否已存在（同 novel + 同章节号）
        existing = session.query(Chapter).filter(
            Chapter.novel_id == novel_id,
            Chapter.number == number,
        ).first()
        if existing:
            existing.title = title
            existing.summary = summary
            existing.content = content
            existing.word_count = len(content)
            existing.version += 1
            session.commit()
            return existing.id
        else:
            chapter = Chapter(
                novel_id=novel_id, volume=volume, number=number,
                title=title, summary=summary, content=content,
                word_count=len(content),
            )
            session.add(chapter)
            session.commit()
            return chapter.id


def db_get_chapter(novel_id: int, chapter_no: int) -> dict:
    """获取指定章节内容"""
    with get_session() as session:
        ch = session.query(Chapter).filter(
            Chapter.novel_id == novel_id, Chapter.number == chapter_no
        ).first()
        if not ch:
            return {}
        return {
            "id": ch.id, "volume": ch.volume, "number": ch.number,
            "title": ch.title, "summary": ch.summary, "content": ch.content,
            "word_count": ch.word_count, "status": ch.status, "version": ch.version,
        }


def db_get_recent_chapters(novel_id: int, count: int = 3) -> list[dict]:
    """获取最近 N 章内容（写作时提供上下文）"""
    with get_session() as session:
        chapters = session.query(Chapter).filter(
            Chapter.novel_id == novel_id
        ).order_by(Chapter.number.desc()).limit(count).all()
        return [
            {"number": c.number, "title": c.title, "content": c.content[-1500:]}
            for c in reversed(chapters)
        ]


def db_get_all_chapters(novel_id: int) -> list[dict]:
    """获取小说的所有章节"""
    with get_session() as session:
        chapters = session.query(Chapter).filter(
            Chapter.novel_id == novel_id
        ).order_by(Chapter.number).all()
        return [
            {"number": c.number, "title": c.title, "content": c.content,
             "word_count": c.word_count, "status": c.status}
            for c in chapters
        ]


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def parse_json_response(text: str) -> dict:
    """从 LLM 回复中提取 JSON（处理 markdown 代码块包裹的情况）"""
    text = text.strip()
    # 去掉 markdown 代码块标记
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return json.loads(text.strip())
