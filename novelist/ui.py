"""
Novelist Web UI — 基于 Streamlit 的小说书架、搜索、创作、编辑界面

启动方式: streamlit run novelist/ui.py
"""

import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from datetime import datetime

from novelist.agents import SearchAgent, WriterAgent, EditorAgent
from novelist.graph import run_novel_workflow
from novelist.tools import (
    db_get_novel, db_get_all_chapters, db_get_chapter, db_save_chapter,
    write_file,
)
from novelist.models import init_db, get_session, Novel, Chapter

# 页面配置
st.set_page_config(
    page_title="Novelist — AI 小说平台",
    page_icon="📖",
    layout="wide",
)

# 初始化数据库
init_db()


# ═══════════════════════════════════════════
# 侧边栏导航
# ═══════════════════════════════════════════

st.sidebar.title("📖 Novelist")
st.sidebar.caption("AI 小说阅读与创作平台")

page = st.sidebar.radio(
    "导航",
    ["📚 我的书架", "🔍 搜索小说", "✍️ AI 创作", "✏️ 编辑修改"],
)


# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

def get_all_novels():
    """获取所有小说列表"""
    with get_session() as session:
        return session.query(Novel).order_by(Novel.created_at.desc()).all()


def build_novel_markdown(novel_id: int) -> str:
    """将小说编译为 Markdown"""
    chapters = db_get_all_chapters(novel_id)
    novel = db_get_novel(novel_id)

    lines = [f"# {novel.get('title', '未命名')}", ""]
    for ch in chapters:
        lines.append(f"## 第{ch['number']}章 {ch['title']}")
        lines.append("")
        lines.append(ch["content"])
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════
# 页面1: 我的书架
# ═══════════════════════════════════════════

if page == "📚 我的书架":
    st.title("📚 我的书架")

    novels = get_all_novels()

    if not novels:
        st.info("书架上还没有小说。去「✍️ AI 创作」写一本吧！")
    else:
        # 小说列表
        for novel in novels:
            chapters = db_get_all_chapters(novel.id)
            total_words = sum(c["word_count"] for c in chapters)

            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.subheader(f"《{novel.title}》")
                    st.caption(
                        f"{novel.genre or '未分类'} | {novel.theme or '无主题'} | "
                        f"{len(chapters)}章 · {total_words}字 | "
                        f"创建于 {novel.created_at.strftime('%Y-%m-%d %H:%M')}"
                    )
                with col2:
                    if st.button("📖 阅读", key=f"read_{novel.id}"):
                        st.session_state.reading_novel = novel.id
                        st.session_state.reading_chapter = 1
                        st.rerun()
                with col3:
                    if st.button("📥 导出", key=f"export_{novel.id}"):
                        md = build_novel_markdown(novel.id)
                        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                        path = write_file(f"output/{date_str}_{novel.title}.md", md)
                        st.success(f"已导出到 {path}")
                st.divider()

    # 阅读模式
    if "reading_novel" in st.session_state and st.session_state.reading_novel:
        st.divider()
        st.subheader("📖 阅读器")

        novel_id = st.session_state.reading_novel
        novel = db_get_novel(novel_id)
        chapters = db_get_all_chapters(novel_id)

        # 章节选择
        chapter_nos = [c["number"] for c in chapters]
        current_ch = st.selectbox(
            f"《{novel.get('title', '')}》— 选择章节",
            chapter_nos,
            index=st.session_state.reading_chapter - 1,
            key="chapter_selector",
        )
        st.session_state.reading_chapter = current_ch

        # 显示章节内容
        chapter = db_get_chapter(novel_id, current_ch)
        if chapter:
            st.markdown(f"### 第{current_ch}章 {chapter['title']}")
            st.caption(f"字数: {chapter['word_count']} | 版本: v{chapter['version']}")
            st.markdown(chapter["content"])

            # 导航按钮
            c1, c2, c3 = st.columns(3)
            with c1:
                if current_ch > 1 and st.button("⬅ 上一章"):
                    st.session_state.reading_chapter = current_ch - 1
                    st.rerun()
            with c3:
                if current_ch < len(chapters) and st.button("下一章 ➡"):
                    st.session_state.reading_chapter = current_ch + 1
                    st.rerun()

        if st.button("关闭阅读器"):
            del st.session_state.reading_novel
            del st.session_state.reading_chapter
            st.rerun()


# ═══════════════════════════════════════════
# 页面2: 搜索小说
# ═══════════════════════════════════════════

elif page == "🔍 搜索小说":
    st.title("🔍 搜索小说")
    st.caption("联网搜索互联网上的小说资源")

    query = st.text_input("输入你想看的小说类型或关键词", placeholder="例如: 开局满级的无敌文")

    if query and st.button("搜索", type="primary"):
        with st.spinner("正在搜索..."):
            agent = SearchAgent()
            results = agent.search(query, max_results=10)

        if results:
            st.success(f"找到 {len(results)} 条结果")
            for i, r in enumerate(results, 1):
                with st.container():
                    col1, col2 = st.columns([5, 1])
                    with col1:
                        st.markdown(f"**{i}. {r['title']}**")
                        st.caption(r["url"])
                        st.text(r["snippet"][:200])
                    with col2:
                        if st.button("📥 导入", key=f"import_{i}"):
                            with st.spinner("正在导入..."):
                                try:
                                    from novelist.agents import ImportAgent
                                    agent = ImportAgent()
                                    result = agent.import_from_url(r["url"])
                                    if result.get("warning"):
                                        st.warning(f"部分导入: {result['warning']}")
                                    else:
                                        st.success(f"✅ 《{result['title']}》已导入书架!")
                                except Exception as e:
                                    st.error(f"导入失败: {e}")
                    st.divider()
        else:
            st.warning("未找到相关结果，换个关键词试试")


# ═══════════════════════════════════════════
# 页面3: AI 创作
# ═══════════════════════════════════════════

elif page == "✍️ AI 创作":
    st.title("✍️ AI 创作")

    tab1, tab2 = st.tabs(["📝 长篇创作", "⚡ 快速短篇"])

    # Tab 1: 长篇（多 Agent）
    with tab1:
        st.subheader("多 Agent 协作长篇小说")

        col1, col2 = st.columns(2)
        with col1:
            genre = st.text_input("题材", placeholder="玄幻、都市、科幻...", key="long_genre")
            theme = st.text_input("主题", placeholder="逆天改命、星际殖民...", key="long_theme")
            style = st.text_input("写作风格", placeholder="热血、轻松、悬疑...", key="long_style")
        with col2:
            protagonist = st.text_input("主角设定", placeholder="姓名、性格、背景...", key="long_protagonist")
            chapters = st.slider("章节数", 2, 20, 5, key="long_chapters")
            words = st.slider("每章字数", 500, 5000, 1500, 200, key="long_words")
        extra = st.text_area("额外要求", placeholder="其他特殊需求...", key="long_extra")

        if st.button("🚀 开始创作", type="primary", use_container_width=True):
            if not genre and not theme:
                st.error("至少填写题材或主题")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()

                status_text.text("正在分析需求...")
                progress_bar.progress(10)

                try:
                    result = run_novel_workflow(
                        genre=genre,
                        theme=theme,
                        style=style,
                        protagonist=protagonist,
                        chapters=chapters,
                        words_per_chapter=words,
                        extra=extra,
                    )

                    progress_bar.progress(100)
                    status_text.text("✅ 创作完成！")

                    st.success(f"《{result['plan'].get('title', '未命名')}》创作完成！")
                    st.info(f"已完成 {result['current_chapter']} 章 · 数据库 ID: {result['novel_id']}")

                    md = build_novel_markdown(result["novel_id"])
                    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    path = write_file(f"output/{date_str}_{result['plan'].get('title', '小说')}.md", md)

                    try:
                        from novelist.memory import add_all_chapters
                        add_all_chapters(result["novel_id"])
                    except Exception:
                        pass

                    st.success(f"已导出到 {path}")

                    ch1 = db_get_chapter(result["novel_id"], 1)
                    if ch1:
                        with st.expander("📖 预览第一章", expanded=True):
                            st.markdown(f"### 第1章 {ch1['title']}")
                            st.markdown(ch1["content"][:1000] + ("..." if len(ch1["content"]) > 1000 else ""))

                except Exception as e:
                    progress_bar.progress(100)
                    status_text.text("❌ 创作失败")
                    st.error(f"创作过程中出现错误: {e}")

    # Tab 2: 短篇（单 Agent）
    with tab2:
        st.subheader("单 Agent 快速短篇")

        col1, col2 = st.columns(2)
        with col1:
            s_genre = st.text_input("题材", placeholder="玄幻", key="short_genre")
            s_theme = st.text_input("主题", placeholder="剑道之路", key="short_theme")
        with col2:
            s_style = st.text_input("写作风格", key="short_style")
            s_length = st.slider("字数", 300, 5000, 1000, 100, key="short_length")
        s_extra = st.text_area("额外要求", key="short_extra")

        if st.button("⚡ 快速生成", type="primary", use_container_width=True):
            if not s_genre and not s_theme:
                st.error("至少填写题材或主题")
            else:
                with st.spinner("正在创作..."):
                    try:
                        agent = WriterAgent()
                        content = agent.write(
                            genre=s_genre, theme=s_theme, style=s_style,
                            length=s_length, extra=s_extra,
                        )
                        filepath = agent.save(content, title=s_theme or s_genre or "短篇")
                        st.success(f"已保存到 {filepath}")
                        st.markdown(content)
                    except Exception as e:
                        st.error(f"创作失败: {e}")


# ═══════════════════════════════════════════
# 页面4: 编辑修改
# ═══════════════════════════════════════════

elif page == "✏️ 编辑修改":
    st.title("✏️ 编辑修改")
    st.caption("对已有小说的章节进行 AI 修改优化")

    # 选择小说
    novels = get_all_novels()
    if not novels:
        st.info("还没有小说，先去创作一本吧！")
    else:
        novel_options = {f"[{n.id}] {n.title}": n.id for n in novels}
        selected = st.selectbox("选择小说", list(novel_options.keys()))
        novel_id = novel_options[selected]

        novel = db_get_novel(novel_id)
        chapters = db_get_all_chapters(novel_id)

        if not chapters:
            st.warning("这本小说还没有章节")
        else:
            # 选择章节
            chapter_no = st.selectbox(
                "选择要修改的章节",
                [c["number"] for c in chapters],
                format_func=lambda n: f"第{n}章 {chapters[n-1]['title']} ({chapters[n-1]['word_count']}字)",
            )

            # 显示原始内容
            chapter = db_get_chapter(novel_id, chapter_no)
            if chapter:
                with st.expander("📄 原始内容", expanded=False):
                    st.markdown(chapter["content"])

                # 修改意见
                feedback = st.text_area(
                    "修改意见",
                    placeholder="描述你想要的修改，例如:\n- 打斗场面不够精彩，加入更多细节\n- 主角的性格太软弱了，让他更果断一些\n- 结尾太仓促，增加一个反转",
                    height=100,
                )

                if st.button("🔧 执行修改", type="primary", use_container_width=True):
                    if not feedback:
                        st.error("请填写修改意见")
                    else:
                        with st.spinner(f"正在修改第{chapter_no}章..."):
                            try:
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

                                # 更新向量索引
                                try:
                                    from novelist.memory import add_chapter
                                    add_chapter(novel_id, chapter_no, chapter["title"], new_content)
                                except Exception:
                                    pass

                                st.success(
                                    f"修改完成！原{chapter['word_count']}字 → 新{len(new_content)}字"
                                )

                                with st.expander("📝 修改后内容", expanded=True):
                                    st.markdown(new_content)

                            except Exception as e:
                                st.error(f"修改失败: {e}")


# ═══════════════════════════════════════════
# 底部
# ═══════════════════════════════════════════

st.sidebar.divider()
st.sidebar.caption("Powered by DeepSeek + LangGraph + ChromaDB")
