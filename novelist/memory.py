"""
记忆系统 — 向量存储 + 语义检索（ChromaDB + ONNX Embedding）

功能：
- 将章节内容向量化存储
- 写作时检索前文相关段落，保持长文本一致性
"""

from pathlib import Path
import chromadb

# 存储路径
DB_DIR = Path(__file__).parent.parent / "chroma_db"

# 全局实例（延迟初始化）
_embedding_fn = None
_collection = None


def _get_embedding_fn():
    """
    获取 Embedding 函数。
    使用 ChromaDB 内置 ONNX 模型（无需网络下载，开箱即用）。
    注意：内置模型为英文 all-MiniLM-L6-v2，中文语义检索效果有限。
    如需更好的中文效果，可在网络可用时替换为 BGE 模型。
    """
    global _embedding_fn
    if _embedding_fn is None:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        _embedding_fn = DefaultEmbeddingFunction()
    return _embedding_fn


def _get_collection(name: str = "novel_chapters"):
    """获取或创建 ChromaDB 集合"""
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(
            path=str(DB_DIR),
        )
        _collection = client.get_or_create_collection(
            name=name,
            embedding_function=_get_embedding_fn(),
            metadata={"hnsw:space": "cosine"},  # 余弦相似度
        )
    return _collection


def add_chapter(novel_id: int, chapter_no: int, title: str, content: str) -> None:
    """
    将章节分段存入向量数据库。
    每段最多 500 字，方便检索时精准匹配。
    """
    col = _get_collection()

    # 分段（按段落切分，每段不超过 500 字）
    paragraphs = content.split("\n\n")
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current_chunk) + len(para) < 500:
            current_chunk += para + "\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = para + "\n"
    if current_chunk:
        chunks.append(current_chunk.strip())

    if not chunks:
        return

    # 清理该章节旧分段（按 ID 前缀匹配删除，避免复杂 filter 语法）
    existing_ids = col.get()["ids"]
    prefix = f"n{novel_id}_ch{chapter_no}_"
    old_ids = [i for i in existing_ids if i.startswith(prefix)]
    if old_ids:
        col.delete(ids=old_ids)

    ids = [f"n{novel_id}_ch{chapter_no}_p{i}" for i in range(len(chunks))]
    metadatas = [{
        "novel_id": novel_id,
        "chapter_no": chapter_no,
        "title": title,
    } for _ in chunks]

    col.add(documents=chunks, ids=ids, metadatas=metadatas)


def search_similar(query: str, novel_id: int | None = None, top_k: int = 5) -> list[dict]:
    """
    语义检索：查找与 query 最相似的章节段落。

    Args:
        query: 搜索内容
        novel_id: 限定在某本小说内（None 则全局搜索）
        top_k: 返回结果数

    Returns:
        [{"content": "...", "chapter_no": 1, "title": "...", "score": 0.95}, ...]
    """
    col = _get_collection()

    where = {"novel_id": novel_id} if novel_id else None

    try:
        results = col.query(query_texts=[query], n_results=top_k, where=where)
    except Exception:
        return []

    items = []
    if results.get("documents") and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            dist = results["distances"][0][i] if results.get("distances") else 0
            items.append({
                "content": doc[:500],
                "chapter_no": meta.get("chapter_no", 0),
                "title": meta.get("title", ""),
                "score": round(1 - dist, 4) if dist else 0,
            })
    return items


def add_all_chapters(novel_id: int) -> int:
    """
    将数据库中某本小说的所有章节存入向量库。
    Returns: 存入的章节数
    """
    from novelist.tools import db_get_all_chapters

    chapters = db_get_all_chapters(novel_id)
    for ch in chapters:
        add_chapter(novel_id, ch["number"], ch["title"], ch["content"])
    return len(chapters)


def clear_collection():
    """清空向量库（调试用）"""
    col = _get_collection()
    ids = col.get()["ids"]
    if ids:
        col.delete(ids=ids)
