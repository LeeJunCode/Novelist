"""
LangGraph 工作流 — 多 Agent 协作创作小说

流程（含 Self-Reflection）:
  规划 → 角色设计 → 大纲 → [开始章节 → 写作 → 自我反思 →（自查通过？）
    → 外部审核 →（外部通过？）→ 保存 → 下一章] 循环 → 完成
"""

from typing import TypedDict
from langgraph.graph import StateGraph, END

from novelist.agents import (
    PlannerAgent, CharacterAgent, OutlinerAgent,
    NovelWriterAgent, ReviewerAgent, SelfReflectionAgent,
)
from novelist.tools import (
    db_create_novel, db_update_novel,
    db_save_characters, db_query_characters,
    db_save_chapter, db_get_recent_chapters,
)
from novelist.models import init_db


# ═══════════════════════════════════════════
# 状态定义
# ═══════════════════════════════════════════

class NovelState(TypedDict):
    """小说创作工作流的状态"""
    # 用户输入
    genre: str
    theme: str
    style: str
    protagonist: str
    chapters_count: int
    words_per_chapter: int
    extra: str

    # 中间产物
    novel_id: int
    plan: dict
    characters: list[dict]
    outline: list[dict]

    # 逐章写作循环
    current_chapter: int
    chapter_title: str
    chapter_summary: str
    chapter_content: str
    review_result: dict          # 外部审核结果
    self_reflect_result: dict    # 自我反思结果
    revision_count: int          # 外部审核修改次数
    self_reflection_count: int   # 自我反思修改次数

    # 输出
    messages: list[str]
    completed: bool


# ═══════════════════════════════════════════
# 节点函数
# ═══════════════════════════════════════════

def node_plan(state: NovelState) -> NovelState:
    """创作规划"""
    agent = PlannerAgent()
    plan = agent.plan(
        genre=state["genre"], theme=state["theme"],
        style=state["style"], protagonist=state["protagonist"],
        chapters=state["chapters_count"],
        words_per_chapter=state["words_per_chapter"],
        extra=state.get("extra", ""),
    )
    novel_id = db_create_novel(
        title=plan.get("title", "未命名"),
        genre=state["genre"], theme=state["theme"], style=state["style"],
    )
    state["novel_id"] = novel_id
    state["plan"] = plan
    state["messages"] = [
        f"📖 小说标题：《{plan.get('title', '未命名')}》",
        f"📝 情节概要：{plan.get('plot_summary', '')[:100]}...",
    ]
    print(f"  ✅ 创作方案 → 《{plan.get('title', '未命名')}》")
    return state


def node_design_characters(state: NovelState) -> NovelState:
    """设计角色"""
    agent = CharacterAgent()
    result = agent.design(state["plan"])
    characters = result.get("characters", [])
    db_save_characters(state["novel_id"], characters)
    state["characters"] = characters
    state["messages"].append(f"👥 已创建 {len(characters)} 个角色")
    print(f"  ✅ 角色设计 → {len(characters)} 个角色")
    return state


def node_outline(state: NovelState) -> NovelState:
    """生成大纲"""
    agent = OutlinerAgent()
    result = agent.outline(state["plan"], state["characters"])
    outline = result.get("outline", [])
    state["outline"] = outline
    state["messages"].append(f"📋 已生成 {len(outline)} 章大纲")
    print(f"  ✅ 大纲生成 → {len(outline)} 章")
    return state


def node_start_chapter(state: NovelState) -> NovelState:
    """准备新章节"""
    chapter_no = state.get("current_chapter", 0) + 1
    outline = state["outline"]
    if chapter_no <= len(outline):
        ch_info = outline[chapter_no - 1]
        title = ch_info.get("title", f"第{chapter_no}章")
        summary = ch_info.get("summary", "")
    else:
        title = f"第{chapter_no}章"
        summary = "继续推进主线情节"

    state["current_chapter"] = chapter_no
    state["chapter_title"] = title
    state["chapter_summary"] = summary
    state["chapter_content"] = ""
    state["review_result"] = {}
    state["self_reflect_result"] = {}
    state["revision_count"] = 0
    state["self_reflection_count"] = 0

    print(f"\n  📝 第{chapter_no}章：{title}")
    return state


def node_write(state: NovelState) -> NovelState:
    """写章节"""
    agent = NovelWriterAgent()
    content = agent.write_chapter(
        novel_id=state["novel_id"],
        chapter_no=state["current_chapter"],
        chapter_title=state["chapter_title"],
        chapter_summary=state["chapter_summary"],
        word_count=state["words_per_chapter"],
        style=state.get("style", ""),
        genre=state.get("genre", ""),
    )
    state["chapter_content"] = content
    return state


def node_self_reflect(state: NovelState) -> NovelState:
    """Self-Reflection: 写完自查自评"""
    agent = SelfReflectionAgent()
    result = agent.reflect(
        chapter_content=state["chapter_content"],
        chapter_summary=state["chapter_summary"],
        target_word_count=state["words_per_chapter"],
        characters=state["characters"],
    )
    state["self_reflect_result"] = result
    state["self_reflection_count"] += 1

    score = result.get("score", 0)
    passed = result.get("passed", False)
    print(f"  🔍 自我反思: 评分 {score}/10 {'✅ 通过' if passed else '❌ 需修改'}")

    if not passed:
        problems = result.get("problems", [])
        for p in problems[:3]:
            print(f"     ⚡ [{p.get('severity')}] {p.get('description', '')[:60]}")
    return state


def node_review(state: NovelState) -> NovelState:
    """外部审核（Reviewer Agent）"""
    agent = ReviewerAgent()
    ch_no = state["current_chapter"]
    outline = state["outline"]
    prev_summary = outline[ch_no - 2]["summary"][:200] if ch_no > 1 else "（无）"
    next_summary = outline[ch_no]["summary"][:200] if ch_no < len(outline) else "（最后一章）"
    outline_context = f"前一章大纲：{prev_summary}\n本章大纲：{state['chapter_summary']}\n后一章大纲：{next_summary}"

    result = agent.review(
        chapter_content=state["chapter_content"],
        chapter_summary=state["chapter_summary"],
        outline_context=outline_context,
        characters=state["characters"],
        target_word_count=state["words_per_chapter"],
    )
    state["review_result"] = result
    state["revision_count"] += 1

    score = result.get("score", 0)
    passed = result.get("passed", False)
    print(f"  📋 外部审核: 评分 {score}/10 {'✅ 通过' if passed else '❌ 需修改'}")
    return state


def node_save_chapter(state: NovelState) -> NovelState:
    """保存章节"""
    db_save_chapter(
        novel_id=state["novel_id"], volume=1,
        number=state["current_chapter"],
        title=state["chapter_title"],
        summary=state["chapter_summary"],
        content=state["chapter_content"],
    )
    print(f"  💾 第{state['current_chapter']}章已保存")
    return state


# ═══════════════════════════════════════════
# 路由决策
# ═══════════════════════════════════════════

def decide_after_self_reflect(state: NovelState) -> str:
    """自我反思后：通过则送外部审核，不通过则自我修改（最多2次）"""
    result = state["self_reflect_result"]

    if result.get("passed", False) or result.get("score", 0) >= 7:
        return "to_review"

    if state["self_reflection_count"] >= 2:
        # 自我修改已达上限，送外部审核
        print(f"  ⚠️  自我修改已达2次上限，送外部审核")
        return "to_review"

    return "self_revise"


def decide_after_review(state: NovelState) -> str:
    """外部审核后：通过→保存，不通过→修改（最多3次），超过→强制保存"""
    review = state["review_result"]

    if review.get("passed", False):
        return "save_and_continue" if state["current_chapter"] < state["chapters_count"] else "save_and_finish"

    if state["revision_count"] >= 3:
        print(f"  ⚠️  外部修改已达3次上限，强制通过")
        return "save_and_continue" if state["current_chapter"] < state["chapters_count"] else "save_and_finish"

    issues = review.get("issues", [])
    for issue in issues:
        print(f"  🔧 [{issue.get('type')}] {issue.get('description', '')[:60]}")
    return "revise"


# ═══════════════════════════════════════════
# 构建工作流图
# ═══════════════════════════════════════════

def build_novel_graph() -> StateGraph:
    """构建小说创作 LangGraph 工作流（含 Self-Reflection）"""
    workflow = StateGraph(NovelState)

    # 节点
    workflow.add_node("plan", node_plan)
    workflow.add_node("characters", node_design_characters)
    workflow.add_node("outline", node_outline)
    workflow.add_node("start_chapter", node_start_chapter)
    workflow.add_node("write", node_write)
    workflow.add_node("self_reflect", node_self_reflect)
    workflow.add_node("review", node_review)
    workflow.add_node("save_chapter", node_save_chapter)

    # 边
    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "characters")
    workflow.add_edge("characters", "outline")
    workflow.add_edge("outline", "start_chapter")
    workflow.add_edge("start_chapter", "write")

    # 写完 → 自我反思
    workflow.add_edge("write", "self_reflect")

    # 自我反思 → 通过送审核 / 不通过自我修改
    workflow.add_conditional_edges(
        "self_reflect",
        decide_after_self_reflect,
        {
            "to_review": "review",
            "self_revise": "write",  # 回到写节点自我修改
        },
    )

    # 外部审核 → 通过保存 / 不通过修改
    workflow.add_conditional_edges(
        "review",
        decide_after_review,
        {
            "revise": "write",
            "save_and_continue": "save_chapter",
            "save_and_finish": "save_chapter",
        },
    )

    # 保存后 → 继续或结束
    workflow.add_conditional_edges(
        "save_chapter",
        lambda s: "continue" if s["current_chapter"] < s["chapters_count"] else "end",
        {"continue": "start_chapter", "end": END},
    )

    return workflow


def run_novel_workflow(
    genre: str = "",
    theme: str = "",
    style: str = "",
    protagonist: str = "",
    chapters: int = 5,
    words_per_chapter: int = 2000,
    extra: str = "",
) -> dict:
    """运行小说创作工作流"""
    init_db()

    initial_state: NovelState = {
        "genre": genre, "theme": theme, "style": style,
        "protagonist": protagonist, "chapters_count": chapters,
        "words_per_chapter": words_per_chapter, "extra": extra,
        "novel_id": 0, "plan": {}, "characters": [], "outline": [],
        "current_chapter": 0,
        "chapter_title": "", "chapter_summary": "", "chapter_content": "",
        "review_result": {}, "self_reflect_result": {},
        "revision_count": 0, "self_reflection_count": 0,
        "messages": [], "completed": False,
    }

    graph = build_novel_graph()
    app = graph.compile()
    return app.invoke(initial_state)
