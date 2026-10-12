"""Agent 定义 — 创作规划、角色设计、大纲生成、章节写作、质量审核"""

import yaml
from pathlib import Path
from datetime import datetime

from novelist.llm import chat
from novelist.tools import (
    web_search, parse_json_response,
    db_create_novel, db_update_novel, db_get_novel,
    db_save_characters, db_query_characters,
    db_save_chapter, db_get_chapter, db_get_recent_chapters,
    write_file,
)


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _load_prompt(name: str) -> str:
    """从 YAML 加载 Agent 的 system prompt"""
    path = Path(__file__).parent / "prompts" / f"{name}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)[name]["system"]


def _call_json(system_prompt: str, user_message: str) -> dict:
    """调用 LLM 并解析 JSON 返回"""
    raw = chat(system_prompt, user_message, temperature=0.7, max_tokens=4096)
    return parse_json_response(raw)


# ═══════════════════════════════════════════
# Phase 1 保留：SearchAgent / WriterAgent
# ═══════════════════════════════════════════

class SearchAgent:
    """搜索 Agent — 联网搜索小说"""

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        if "小说" not in query:
            query = f"{query} 小说"
        return web_search(query, max_results=max_results)


class WriterAgent:
    """简单写作 Agent — 单次生成短篇（Phase 1 兼容）"""

    def __init__(self):
        self.system_prompt = _load_prompt("writer")

    def write(self, genre="", theme="", style="", protagonist="", length=1500, extra="") -> str:
        parts = ["请帮我创作一篇小说。"]
        if genre:
            parts.append(f"题材：{genre}")
        if theme:
            parts.append(f"主题：{theme}")
        if style:
            parts.append(f"写作风格：{style}")
        if protagonist:
            parts.append(f"主角设定：{protagonist}")
        if length:
            parts.append(f"字数要求：约{length}字")
        if extra:
            parts.append(f"额外要求：{extra}")
        return chat(self.system_prompt, "。".join(parts) + "。", temperature=0.85, max_tokens=max(length * 4, 4096))

    def save(self, content: str, title: str = "") -> str:
        first_line = content.strip().split("\n")[0].lstrip("#").strip()
        title = title or (first_line[:30] if first_line else "untitled")
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{title}.md"
        filepath = Path("output") / filename
        write_file(filepath, content)
        return str(filepath)


# ═══════════════════════════════════════════
# Phase 2：多 Agent 协作
# ═══════════════════════════════════════════

class PlannerAgent:
    """
    创作规划 Agent — 分析用户需求，输出创作方案。

    输入: 用户的创作需求（题材、主题、风格等）
    输出: 结构化的创作方案 (JSON)
    """

    def __init__(self):
        self.system_prompt = _load_prompt("planner")

    def plan(self, genre="", theme="", style="", protagonist="", chapters=10, words_per_chapter=2000, extra="") -> dict:
        """分析需求，生成创作方案"""
        parts = ["请为以下创作需求制定方案："]
        if genre:
            parts.append(f"题材：{genre}")
        if theme:
            parts.append(f"主题：{theme}")
        if style:
            parts.append(f"风格：{style}")
        if protagonist:
            parts.append(f"主角：{protagonist}")
        parts.append(f"计划章节数：{chapters}章，每章{words_per_chapter}字")
        if extra:
            parts.append(f"补充要求：{extra}")

        user_msg = "。".join(parts) + "。"
        return _call_json(self.system_prompt, user_msg)


class CharacterAgent:
    """
    角色设计 Agent — 根据创作方案设计角色档案。

    输入: 创作方案 (plan dict)
    输出: 角色列表 (JSON)
    """

    def __init__(self):
        self.system_prompt = _load_prompt("character")

    def design(self, plan: dict) -> dict:
        """根据创作方案设计角色"""
        user_msg = f"""
        请根据以下创作方案设计角色：

        标题：{plan.get('title', '')}
        题材：{plan.get('genre', '')}
        主题：{plan.get('theme', '')}
        主角设定参考：{plan.get('protagonist_design', '')}
        配角建议：{', '.join(plan.get('supporting_characters', []))}
        反派设计参考：{plan.get('antagonist_design', '')}
        世界观：{plan.get('world_setting', '')}
        """
        return _call_json(self.system_prompt, user_msg)


class OutlinerAgent:
    """
    大纲 Agent — 生成详细章节大纲。

    输入: 创作方案 + 角色列表
    输出: 章节大纲列表 (JSON)
    """

    def __init__(self):
        self.system_prompt = _load_prompt("outliner")

    def outline(self, plan: dict, characters: list[dict]) -> dict:
        """生成章节大纲"""
        # 简化角色信息为摘要
        char_summary = "\n".join(
            f"- {c['name']}（{c['role_type']}）：{c['personality'][:60]}"
            for c in characters
        )

        user_msg = f"""
        请为以下小说生成章节大纲：

        【基本信息】
        标题：{plan.get('title', '')}
        题材：{plan.get('genre', '')}
        主题：{plan.get('theme', '')}
        风格：{plan.get('style', '')}
        情节概要：{plan.get('plot_summary', '')}
        章节数：{plan.get('total_chapters', 10)}章，每章约{plan.get('chapter_word_count', 2000)}字

        【角色列表】
        {char_summary}
        """
        return _call_json(self.system_prompt, user_msg)


class NovelWriterAgent:
    """
    小说写作 Agent（多 Agent 版）— 逐章写作，带上下文感知。

    与 Phase 1 的 WriterAgent 不同，这个 Agent 在写作每章时会：
    1. 查询本章大纲
    2. 查询出场角色信息
    3. 查询最近几章内容（保持连续性）
    4. 按字数要求写作
    """

    def __init__(self):
        self.system_prompt = _load_prompt("writer")

    def write_chapter(
        self,
        novel_id: int,
        chapter_no: int,
        chapter_title: str,
        chapter_summary: str,
        word_count: int,
        style: str = "",
        genre: str = "",
    ) -> str:
        """
        写一个章节。

        Args:
            novel_id: 小说 ID（用于查询上下文）
            chapter_no: 章节序号
            chapter_title: 章节标题
            chapter_summary: 本章大纲摘要
            word_count: 目标字数
            style: 写作风格
            genre: 题材

        Returns:
            章节正文
        """
        # 获取上下文：最近几章 + 出场角色
        recent = db_get_recent_chapters(novel_id, count=3)
        characters = db_query_characters(novel_id)

        # 拼接上下文
        context_parts = [f"【本章任务】\n标题：{chapter_title}\n摘要：{chapter_summary}\n目标字数：{word_count}字"]

        if genre:
            context_parts.append(f"\n【题材】{genre}")
        if style:
            context_parts.append(f"\n【风格要求】{style}")

        if characters:
            chars_text = "\n".join(
                f"- {c['name']}（{c['role_type']}）：性格{c['personality'][:80]}；背景{c['background'][:80]}"
                for c in characters
            )
            context_parts.append(f"\n【角色档案】\n{chars_text}")

        if recent:
            recent_text = "\n---\n".join(
                f"第{c['number']}章 {c['title']}\n{c['content'][-800:]}"
                for c in recent
            )
            context_parts.append(f"\n【前文回顾（最近几章结尾）】\n{recent_text}")

        # RAG 检索：查找与本章大纲语义相似的已有段落（保持风格和设定一致）
        try:
            from novelist.memory import search_similar
            similar = search_similar(chapter_summary, novel_id=novel_id, top_k=3)
            if similar:
                similar_text = "\n---\n".join(
                    f"[第{s['chapter_no']}章] {s['content'][:300]}"
                    for s in similar if s["chapter_no"] != chapter_no
                )
                if similar_text:
                    context_parts.append(f"\n【相似场景参考（保持风格和设定一致）】\n{similar_text}")
        except Exception:
            pass  # 向量库未初始化时跳过，不影响主流程

        context_parts.append("\n请根据以上信息创作本章内容。只输出正文，不要输出其他内容。")
        user_msg = "\n".join(context_parts)

        return chat(
            self.system_prompt,
            user_msg,
            temperature=0.85,
            max_tokens=max(word_count * 4, 4096),
        )


class ReviewerAgent:
    """
    审核 Agent — 审核章节质量，输出修改意见。

    审核通过：passed=True
    需修改：passed=False + issues 列表
    """

    def __init__(self):
        self.system_prompt = _load_prompt("reviewer")

    def review(
        self,
        chapter_content: str,
        chapter_summary: str,
        outline_context: str,
        characters: list[dict],
        target_word_count: int,
    ) -> dict:
        """
        审核章节。

        Args:
            chapter_content: 章节正文
            chapter_summary: 本章大纲摘要
            outline_context: 前后章节大纲（用于检查衔接）
            characters: 出场角色信息
            target_word_count: 目标字数

        Returns:
            审核结果 dict: {passed, score, strengths, issues, summary}
        """
        chars_text = "\n".join(
            f"- {c['name']}：{c['personality'][:100]}"
            for c in characters
        )

        user_msg = f"""
        请审核以下小说章节：

        【本章大纲】
        {chapter_summary}

        【目标字数】{target_word_count}字 | 实际字数：{len(chapter_content)}字

        【前后章节大纲参考】
        {outline_context}

        【角色设定参考】
        {chars_text}

        """
        return _call_json(self.system_prompt, user_msg)


class EditorAgent:
    """
    编辑 Agent — 根据用户意见修改指定章节。

    用法:
        editor = EditorAgent()
        new_content = editor.edit_chapter(
            original_content="...",
            user_feedback="这章打斗不够精彩，加个反转",
            novel_id=1,
            chapter_no=3,
        )
    """

    def __init__(self):
        self.system_prompt = _load_prompt("editor")

    def edit_chapter(
        self,
        original_content: str,
        user_feedback: str,
        novel_id: int,
        chapter_no: int,
    ) -> str:
        """
        根据用户反馈修改章节。

        Args:
            original_content: 原始章节内容
            user_feedback: 用户修改意见
            novel_id: 小说 ID
            chapter_no: 章节序号

        Returns:
            修改后的章节正文
        """
        # 获取上下文
        from novelist.tools import db_get_chapter, db_query_characters

        prev_ch = db_get_chapter(novel_id, chapter_no - 1) if chapter_no > 1 else None
        next_ch = db_get_chapter(novel_id, chapter_no + 1)
        characters = db_query_characters(novel_id)

        # 拼接上下文
        context_parts = [
            f"【章节位置】第{chapter_no}章",
            f"【用户修改意见】{user_feedback}",
        ]

        if characters:
            chars_text = "\n".join(
                f"- {c['name']}（{c['role_type']}）：{c['personality'][:80]}"
                for c in characters
            )
            context_parts.append(f"\n【角色档案】\n{chars_text}")

        if prev_ch:
            context_parts.append(
                f"\n【前一章结尾（确保衔接）】\n{prev_ch['content'][-800:]}"
            )

        if next_ch:
            context_parts.append(
                f"\n【后一章开头（确保衔接）】\n{next_ch['content'][:500]}"
            )

        context_parts.append(f"\n【原始章节内容（请在此基础上修改）】\n---\n{original_content}\n---")
        context_parts.append("\n请根据用户意见修改以上章节，输出完整修改后的正文。")

        return chat(
            self.system_prompt,
            "\n".join(context_parts),
            temperature=0.8,
            max_tokens=len(original_content) * 3,  # 修改可能增加内容
        )


class SelfReflectionAgent:
    """
    Self-Reflection Agent — 写完章节后自查自评，发现问题自我修改。

    这是 Agent 开发中的核心模式：自我反思 → 自我改进循环。
    """

    def __init__(self):
        self.system_prompt = _load_prompt("self_reflect")

    def reflect(
        self,
        chapter_content: str,
        chapter_summary: str,
        target_word_count: int,
        characters: list[dict],
    ) -> dict:
        """审查自己的章节，返回评分和问题列表"""
        chars_text = "\n".join(
            f"- {c['name']}（{c['role_type']}）：{c['personality'][:60]}"
            for c in characters
        ) if characters else "（无）"

        user_msg = f"""
        请审查以下刚写完的章节：

        【本章大纲要求】
        {chapter_summary}

        【目标字数】{target_word_count}字 | 实际字数：{len(chapter_content)}字

        【角色参考】
        {chars_text}

        """
        return _call_json(self.system_prompt, user_msg)


class ImportAgent:
    """
    小说导入 Agent — 抓取网页，用 LLM 提取小说内容并入库。
    """

    SYSTEM_PROMPT = """你是一个专业的网页内容提取器。从给定的 HTML 中提取小说信息。

## 提取规则
1. 忽略 HTML 标签、JS、CSS、广告
2. 找到小说文本内容
3. 判断页面类型：目录页 / 章节页 / 简介页

## 输出 JSON
{
  "page_type": "chapter/catalog/intro",
  "title": "小说标题",
  "author": "作者",
  "chapter_title": "章节标题（章节页时）",
  "content": "正文（用\\n\\n分隔段落）",
  "description": "简介（目录页/简介页时）"
}

正文只提取小说内容，去掉导航、广告、评论。超过5000字截断。"""

    def import_from_url(self, url: str) -> dict:
        """
        从 URL 导入小说。
        Returns: {"novel_id": int, "title": str, ...}
        """
        from novelist.tools import fetch_page, parse_json_response, db_create_novel, db_save_chapter
        from novelist.llm import chat

        # 1. 抓取网页
        html = fetch_page(url)
        html_snippet = html[:15000] if len(html) > 15000 else html

        # 2. LLM 提取内容
        user_msg = f"请从以下网页源码中提取小说信息：\n\nURL: {url}\n\n```html\n{html_snippet}\n```"
        raw = chat(self.SYSTEM_PROMPT, user_msg, temperature=0.3, max_tokens=4096)
        data = parse_json_response(raw)

        # 3. 入库
        title = data.get("title", "未命名导入")
        novel_id = db_create_novel(title=title)

        if data.get("page_type") == "chapter" and data.get("content"):
            content = data["content"].replace("\\n\\n", "\n\n").replace("\\n", "\n")
            db_save_chapter(
                novel_id=novel_id, volume=1, number=1,
                title=data.get("chapter_title", "第1章"), content=content,
            )
            return {
                "novel_id": novel_id, "title": title,
                "author": data.get("author", "未知"),
                "chapter_count": 1, "word_count": len(content),
            }
        elif data.get("description"):
            return {
                "novel_id": novel_id, "title": title,
                "author": data.get("author", "未知"),
                "description": data.get("description", ""), "chapter_count": 0,
            }
        return {
            "novel_id": novel_id, "title": title,
            "author": data.get("author", "未知"),
            "warning": "未能提取到正文内容", "chapter_count": 0,
        }
