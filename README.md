# Novelist（小说家）

> 面向个人使用的 **AI 小说搜索、阅读与创作平台** — 搜小说、写小说、改小说，全流程由多 Agent 协作完成。

Novelist 用 LangGraph 编排 6 个专职 Agent（规划 / 角色 / 大纲 / 写作 / 自省 / 审核），从一句创作需求出发，
自主完成「创作方案 → 角色档案 → 章节大纲 → 逐章写作 → 自查自改 → 外部审核 → 落库 → 向量索引」的完整长篇小说生产闭环。

---

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 🔍 **搜小说** | Agent 联网搜索（DuckDuckGo，失败回退 Bing），按口味筛选作品，支持一键导入书架 |
| ✍️ **写小说** | 多 Agent 协作写长篇，或单 Agent 快速出短篇 |
| ✏️ **改小说** | 按自然语言修改意见重写指定章节，自动读取前后章保证衔接 |
| 📚 **读小说** | Streamlit 分章阅读器（上下章翻页）、Markdown 导出 |
| 🧠 **记忆系统** | ChromaDB 向量库 + 语义检索，写作时自动召回前文相关段落，缓解长篇设定漂移 |
| 🔎 **自我反思** | 写完先自评（评分 + 问题清单），自查不过先自我修改，再交外部审核 |
| 📊 **可观测性** | 可选接入 LangFuse，自动追踪每次 LLM 调用的 token / 延迟 / 成本 |

---

## 技术栈

- **语言**：Python 3.12+
- **LLM**：DeepSeek API（OpenAI 兼容协议）
- **Agent 框架**：LangGraph + LangChain
- **向量库**：ChromaDB（内置 ONNX Embedding，开箱即用，无需额外下载模型）
- **关系库**：SQLite + SQLAlchemy 2.0
- **搜索**：DuckDuckGo（`ddgs`）→ Bing HTML 回退
- **CLI**：Click　|　**Web**：Streamlit

---

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`，填入 DeepSeek 的 Key（[申请地址](https://platform.deepseek.com)）：

```ini
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 以下为可选：LangFuse 可观测性，不配置也能正常运行
LANGFUSE_ENABLED=false
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

### 3. 启动 Web UI（推荐）

```bash
streamlit run novelist/ui.py
```

浏览器打开 <http://localhost:8501>，四个页面：📚 我的书架 / 🔍 搜索小说 / ✍️ AI 创作 / ✏️ 编辑修改。

---

## 使用方式

### Web UI

- **我的书架** — 列出所有小说，一键阅读（分章翻页）或导出 Markdown
- **搜索小说** — 输入关键词联网搜索，结果可「📥 导入」到书架
- **AI 创作** — 「📝 长篇创作」走多 Agent 工作流，「⚡ 快速短篇」单 Agent 直出
- **编辑修改** — 选小说 → 选章节 → 填修改意见 → AI 重写并更新向量索引

### CLI

项目未打包为可执行脚本，统一用 `python -m novelist.main` 调用：

```bash
# 联网搜索小说
python -m novelist.main search "开局满级的无敌文" -n 8

# 多 Agent 创作长篇（题材/主题/风格/主角/章节数/每章字数）
python -m novelist.main write -g 玄幻 -t "逆天改命" -s 热血 -c 10 -w 2000

# 单 Agent 快速短篇
python -m novelist.main write-short -g 玄幻 -t "剑道之路" -l 1500

# 修改指定章节（小说ID 章节号 "修改意见"）
python -m novelist.main edit 1 3 "打斗不够精彩，加一个反转"

# 从网页导入小说
python -m novelist.main import-novel https://example.com/novel/chapter1.html
```

---

## 架构

### 多 Agent 创作工作流

```
                  ┌──────────────────────────────────────────────┐
                  │              LangGraph 状态机                │
                  └──────────────────────────────────────────────┘

  plan ──► characters ──► outline ──► start_chapter ──► write
 规划        角色设计       章节大纲       准备下一章        写作
                                                          │
                                                          ▼
                        ┌────────────────────────► self_reflect
                        │ 自我修改（最多 2 次）        自我反思
                        │                          │
                        │       评分 <7 且未达上限   │  通过 / 评分 ≥7 / 达上限
                        └──────────────────────────┤
                                                   ▼
                                                 review
                                              外部审核
                                                   │
                        ┌──────────────────────────┤  通过 / 修改达 3 次上限
                        │ 重写（最多 3 次）          ▼
                        └────────────────────► save_chapter
                                                    │
                                    还有章节 ◄──────┴──────► 全部完成 → END
                                        │
                                        └──► start_chapter（下一章）
```

**Agent 分工**

| Agent | 职责 | 产出 |
| --- | --- | --- |
| `PlannerAgent` | 分析创作需求，制定方案 | 标题/主题/世界观/情节梗概/主角与反派设计 |
| `CharacterAgent` | 设计角色档案 | 角色列表（性格/背景/能力/外貌/关系） |
| `OutlinerAgent` | 生成章节大纲 | 每章标题 + 摘要 |
| `NovelWriterAgent` | 逐章写作 | 章节正文（携带最近 3 章 + 角色档案 + RAG 召回上下文） |
| `SelfReflectionAgent` | 写后自查 | 评分 + 亮点 + 问题清单（含严重度与修改建议） |
| `ReviewerAgent` | 外部质量审核 | 通过与否 + 评分 + 问题列表 |
| `EditorAgent` | 按用户意见改稿 | 修改后正文（读前一章结尾 + 后一章开头保证衔接） |
| `ImportAgent` | 网页小说导入 | 提取标题/作者/正文并入库 |

**上下文一致性三重保障**：最近 3 章原文 + 全量角色档案 + ChromaDB 语义召回相似段落。

### 状态流转

`self_reflect` 与 `review` 都是条件边：
- 自省 `passed=True` 或 `score ≥ 7` → 送外部审核；否则回 `write` 自我修改，**最多 2 次**
- 审核 `passed=True` → 保存；否则回 `write` 重写，**最多 3 次**，超限强制保存
- 保存后若 `current_chapter < chapters_count` → 回到 `start_chapter` 写下一章，否则 `END`

---

## 项目结构

```
Novelist/
├── novelist/                  # 唯一源码目录
│   ├── main.py                # CLI 入口（search / write / write-short / edit / import-novel）
│   ├── config.py              # pydantic-settings 配置管理
│   ├── llm.py                 # DeepSeek 客户端封装 + LangFuse 追踪
│   ├── agents.py              # 全部 8 个 Agent 定义
│   ├── graph.py               # LangGraph 工作流编排（状态 + 节点 + 条件路由）
│   ├── tools.py               # 工具集：联网搜索、网页抓取、文件读写、数据库 CRUD
│   ├── models.py              # SQLAlchemy 模型：Novel / Character / Chapter
│   ├── memory.py              # ChromaDB 向量存储与语义检索
│   ├── ui.py                  # Streamlit Web 界面
│   └── prompts/               # 各 Agent 的 System Prompt（YAML）
│       ├── planner.yaml  character.yaml  outliner.yaml
│       ├── writer.yaml   reviewer.yaml   self_reflect.yaml
│       └── editor.yaml   importer.yaml
├── output/                    # 生成的小说（Markdown）
├── library/                   # 本地小说存储
├── samples/                   # 写作风格样本（预留）
├── chroma_db/                 # ChromaDB 持久化目录
├── novelist.db                # SQLite 数据库
├── .streamlit/config.toml     # Streamlit 配置
├── Dockerfile / docker-compose.yml / .dockerignore
├── requirements.txt / .env.example
└── CLAUDE.md
```

### 数据模型

- **`Novel`** — 标题、题材、主题、风格、状态（planning/writing/completed）、创建时间
- **`Character`** — 归属小说、姓名、角色类型（protagonist/antagonist/supporting）、性格、背景、能力、外貌、人物关系
- **`Chapter`** — 归属小说、卷号、章节号、标题、大纲摘要、正文、字数、状态、**版本号**（每次修改自增）

---

## Docker 运行（可选）

```bash
docker compose up -d --build
```

访问 <http://localhost:8501>。`output/`、`library/`、`chroma_db/`、`novelist.db` 均挂载到宿主机持久化，
API Key 通过 `env_file: .env` 注入。

> 注：项目定位为本地个人使用，Docker 仅作为可选的部署方式，不影响本地直跑。

## License

个人学习项目，仅供个人使用。
