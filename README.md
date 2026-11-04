# report-rag

财务改完报销制度后，把员工常问的题对旧版、新版各问一遍，列出哪些答案换成了另一套数。那张「变了 / 没变」清单就是交付物。

演示数据为自建可公开复现材料，**不是真审批**，也非真实公司机密。底层仍是 PDF 制度的解析 → 分块 → 向量检索 → 带出处回答；聊天只是尺子，主界面是口径对照表。

仓库地址：<https://github.com/jningc/report-rag>

## 功能特性

- **制度变更影响面**：同一批题对 v1.2 / v1.3 报销稿各问一遍，打出变了 / 没变清单
- **短结论对齐**：回答先给可报 / 不可报 / 条件分支 / 拒答，`should_flip` 对上算过
- **PDF 按页解析**：保留文件名与页码，便于溯源
- **按页切分**：chunk 不跨页合并，出处精确到页
- **FAISS 向量库**：本地 BGE embedding 建库，支持持久化
- **RAG 问答**：LangChain LCEL 编排检索→生成主路径，调用 LLM 生成回答
- **引用出处**：回答附带 `source` / `page`
- **拒答**：检索无结果或相关度过低时不调用 LLM
- **检索层测评**：8 条固定用例自动验证命中与拒答
- **CLI 入口**：`index` 建库 / `ask` 问答 / `eval` 测评 / `index-impact` 双库 / `impact` 对照
- **LangChain Tool**：`search_docs` 封装文档检索，可单独 `invoke` 或供 Agent 调用

## 技术栈

| 环节 | 选型 |
|------|------|
| PDF 解析 | pdfplumber |
| 文本切分 | langchain-text-splitters |
| Embedding | 本地 `BAAI/bge-small-zh-v1.5`（sentence-transformers） |
| 向量库 | FAISS（LangChain 封装） |
| LLM | DevAGI OpenAI 兼容 API（默认 `gpt-3.5-turbo`） |
| RAG 编排 | LangChain LCEL（`retriever \| format_docs \| prompt \| llm`） |
| Web UI | Streamlit（`app.py`） |

Embedding 在本地运行，**建库与检索无需 API Key**；`ask` 仅 LLM 调用需要 DevAGI Key。

## 架构

```mermaid
flowchart LR
    PDF[data/raw_pdfs] --> Loader[docs_loader]
    Loader --> Chunker[chunker]
    Chunker --> Indexer[indexer]
    Indexer --> BGE[BGE 本地 embed]
    BGE --> FAISS[(data/faiss_index)]

    Query[用户问题] --> Score[search_with_scores]
    FAISS --> Score
    Score -->|相关度够| Chain[LCEL Chain]
    Score -->|拒答| Refuse[无法回答]
    FAISS --> Chain
    Chain --> LLM[DevAGI LLM]
    LLM --> Answer[答案 + 出处]
```

## 项目结构

```
report-rag/
├── main.py              # CLI 入口（index / ask / eval / index-impact / impact）
├── app.py               # Streamlit：第一屏对照表，第二页单题问答
├── impact.py            # 同一批题对两库各问一遍，打出对照表
├── docs_loader.py       # PDF 按页读取
├── chunker.py           # 文本切分
├── indexer.py           # 向量化 + FAISS 建库/加载
├── retriever.py         # 相似度检索 + get_retriever（LangChain 接口）
├── rag.py               # RAG 问答（LCEL Chain + ask）
├── tools.py             # LangChain Tool（search_docs）
├── eval.py              # 检索层测评
├── data/
│   ├── raw_pdfs/        # 现行制度 PDF（报销为 v1.3）
│   ├── raw_pdfs_v12/    # 旧版报销稿，不进主库
│   ├── eval_cases.json  # 检索层测评用例
│   ├── eval_impact.json # 影响面题集
│   ├── faiss_index/     # 主库（运行 index 后生成）
│   ├── faiss_index_v12/ # 旧版报销库
│   └── faiss_index_v13/ # 新版报销库
├── .env.example
└── requirements.txt
```

## 快速开始

### 1. 环境准备

```bash
git clone https://github.com/jningc/report-rag
cd report-rag

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

首次建库会从 HuggingFace 下载 BGE 模型（约几百 MB）。网络不稳时可设镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

### 2. 配置 LLM Key（仅 ask 需要）

```bash
cp .env.example .env
```

编辑 `.env`，填入 [DevAGI](https://devcto.com) 的 Key 与端点：

```
DEVAGI_API_KEY=your_devagi_api_key_here
DEVAGI_BASE_URL=https://api.fe8.cn/v1
DEVAGI_MODEL=gpt-3.5-turbo
```

`index` 与 `eval` 不调用 LLM，可不配置 Key（Embedding 为本地 BGE）。

### 3. 建库

PDF 已放在 `data/raw_pdfs/`，执行：

```bash
python main.py index
```

输出示例：

```
共 32 页 → 308 块，开始入库…
已写入: .../data/faiss_index
```

### 4. 问答

```bash
python main.py ask "年假怎么请"
python main.py ask "出差打车怎么报销" -k 5
```

### 5. 检索层测评

```bash
python main.py eval
```

### 6. 影响面对照（旧版 / 新版报销稿）

```bash
python main.py index-impact
python main.py impact
```

同一批题对 `faiss_index_v12`（v1.2）和 `faiss_index_v13`（v1.3）各问一遍，打出变了 / 没变清单。v1.2 PDF 单独放在 `data/raw_pdfs_v12/`，不会打进主库。

### 7. Web 界面（Streamlit）

建库并配置好 `.env` 后：

```bash
streamlit run app.py
```

默认地址：<http://localhost:8501>。打开先看到对照表，不是聊天框；点开一题看旧答、新答、出处版本。单题问答在第二页，当尺子。侧边栏四题：住宿上限、招待后餐补、加班打车、发票抬头。

首次运行 Streamlit 可能在终端询问邮箱，直接按 Enter 跳过即可。

## CLI 用法

```bash
python main.py -h
python main.py index -h
python main.py ask -h
python main.py eval -h
python main.py index-impact
python main.py impact -k 3

python main.py index --pdf-dir /path/to/pdfs
python main.py ask "餐饮报销有什么要求" -k 3
python main.py eval -k 5
python eval.py
```

## Web 界面

```bash
streamlit run app.py
```

| 功能 | 说明 |
|------|------|
| 影响面对照 | 第一屏：该变 / 没变清单，点开看旧答、新答、出处 |
| 运行对照 | 对两库各问一遍；也可先跑 `python main.py impact` |
| 单题问答 | 第二页，当尺子，不当主产品 |
| 检索条数 | 侧边栏 slider 调节 top-k（1–10） |
| 演示四题 | 侧边栏：住宿 600、招待后餐补、加班打车、发票抬头 |
| 索引检查 | 未建影响面库时提示执行 `python main.py index-impact` |

底层复用 `rag.ask()`，需配置 `DEVAGI_API_KEY`。演示数据，不是真审批。

## RAG 主路径（LangChain LCEL）

`ask()` 对外接口不变，内部生成部分已改为 LangChain LCEL Chain：

```
ask(question)
  ├─ search_with_scores     # 拒答判断 + 提取 sources（不调 LLM）
  └─ chain.invoke(question) # LCEL 生成主路径
       retriever | format_docs  →  context
       RunnablePassthrough()    →  question
       | RAG_PROMPT | llm | StrOutputParser()
```

核心函数：

| 函数 | 说明 |
|------|------|
| `get_retriever(k)` | FAISS → LangChain Retriever |
| `format_docs(docs)` | Document 列表 → prompt 参考资料字符串 |
| `build_rag_chain(retriever, llm)` | 组装 LCEL 管道 |
| `ask(question, k)` | 拒答 + `chain.invoke` + 返回 sources |

## search_docs Tool

将文档检索封装为 LangChain Tool，底层复用 `search_with_scores` + `format_docs`，与 `ask()` 共用拒答阈值。

```python
from tools import search_docs

result = search_docs.invoke({"query": "出差打车怎么报销", "k": 3})
print(result)
```

命令行冒烟：

```bash
python tools.py
```

返回示例：

```
[1] 来源: 02_reimbursement.pdf 第1页
出差打车可按实报实销...
```

Tool 与 LCEL Chain 的关系：

| 组件 | 作用 |
|------|------|
| LCEL Chain | `ask()` 固定流程：检索 → 生成 |
| `search_docs` Tool | 独立检索能力，LLM/Agent 可按需调用 |

## 模块说明

| 模块 | 核心函数 | 说明 |
|------|----------|------|
| `docs_loader` | `load_pdfs(folder)` | 读取目录下所有 PDF，每页一条记录 |
| `chunker` | `chunk_pages(pages)` | 按页切分，保留 source/page |
| `indexer` | `build_index(chunks)` | BGE embed + 写入 FAISS 并落盘 |
| `indexer` | `load_index()` | 从本地加载索引 |
| `retriever` | `search(query, k=3)` | 相似度检索 top-k（vectorstore 进程内缓存） |
| `retriever` | `search_with_scores(query, k=3)` | 带相关度分数的检索，供拒答判断 |
| `retriever` | `get_retriever(k=3)` | 返回 LangChain Retriever，供 LCEL 使用 |
| `rag` | `build_rag_chain(retriever, llm)` | LCEL：检索 → prompt → LLM |
| `rag` | `ask(question, k=3)` | 完整 RAG，返回 answer + sources |
| `tools` | `search_docs(query, k=3)` | LangChain Tool，返回检索结果字符串 |
| `eval` | `run_eval(k=3)` | 检索层测评，不调 LLM |
| `impact` | `run_impact(k=3)` | 两库对照，短结论对齐 should_flip |

各模块均可单独冒烟：

```bash
python docs_loader.py
python chunker.py
python indexer.py
python retriever.py
python rag.py
python tools.py
python eval.py
python impact.py
```

## 数据格式

流水线中统一使用 dict 传递：

```python
{"source": "02_reimbursement.pdf", "page": 1, "text": "..."}
```

页码随 metadata 写入 FAISS 的 `index.pkl`，检索时通过 `doc.metadata["page"]` 取回。

## 示例问题

演示四题（影响面主路径）：

| 问题 | 标注 |
|------|------|
| 上海出差住了600一晚，能报多少？ | 该变（500 → 550） |
| 当天客户宴请已经报了，出差餐补还有吗？ | 该变（有 → 没有） |
| 加班到晚上十一点，打车回家能报吗？ | 没变（都不能报） |
| 发票抬头写成我自己的名字，能报吗？ | 没变（抬头必须公司全称） |

## 测评

两层都跑在本机，数字是实测结果，不是估计。检索层不调 LLM，可离线复现。

### 1. 检索层（`python main.py eval`）

8 条固定用例，BGE 本地 embedding + FAISS，k=3，阈值 `MIN_RELEVANCE_SCORE=0.4`。

| 用例类型 | 条数 | 通过 | 结果 |
|----------|------|------|------|
| 正常问题（source 命中且分数达标） | 5 | 4 | 召回 4/5 = 80% |
| 应拒答（无结果或分数低于阈值） | 3 | 3 | 拒答 3/3 = 100% |
| 合计 | 8 | 7 | 87.5% |

唯一失败的是「产品常见问题有哪些」：top_score 0.340 未达 0.4，被判未命中。分数 0.34–0.35 这段是最容易误杀的区间，换 embedding 模型后要重新标阈值。

### 2. 影响面三层（`python main.py impact --offline`）

12 题，v1.2 / v1.3 两版报销稿各答一遍：2 题该变，10 题不该变。逐层算通过，失败的层不往下传。`--offline` 读 `data/impact_last.json` 重算，不调 LLM。

| 层 | 通过 | 说明 |
|----|------|------|
| 检索（两版都要命中对应报销稿） | 11/12 | `purchase_over_500` 两库都没捞到采购条款，按设计降级为拒答，不是编一个答案 |
| schema（短结论字段可解析） | 11/12 | 结论缺「可报/不可报」或金额时判失败 |
| 翻转判定（该变的判变、不该变的判没变） | 9/11 | 该变 2/2 全中，漏报 0；不该变里 2 条误判为变了，误报 2/9 |

两条误报都出在结论表述不一致，不是制度真改了：

- `overtime_commute`：旧版答「可报上限 80」，新版答「不可报」
- `thirty_day_window`：旧版「不可报」，新版「拒答」

根因是「拒答」和「不可报」被当成两个不同结论。下一步把这两个状态在 schema 里分开，字段对齐后再判翻转。

### 3. 失败降级路径

| 失败点 | 系统行为 |
|--------|----------|
| 检索无命中 / top_score < 阈值 | 直接回「根据现有资料无法回答」，不构建 Chain、不调 LLM |
| 检索过但 schema 不齐 | 该题不计入翻转分母，避免拿残缺结论下判断 |
| 翻转判错 | 输出逐题「变了 / 没变」清单和出处，交人工复核，不自动改口 |

阈值在 `rag.py` 的 `MIN_RELEVANCE_SCORE`（当前默认 `0.4`），换 embedding 模型后可能需要微调。

## 设计说明

- **按页切分、不跨页**：保证页码出处准确
- **本地 BGE + 云端 LLM**：建库/检索零 API 费用，仅生成答案消耗 LLM 额度
- **LangChain LCEL 主路径**：`retriever | format_docs | prompt | llm` 标准编排检索→生成
- **拒答前置**：`search_with_scores` 判定相关度，不足时不构建 Chain、不调用 LLM
- **retriever 缓存**：同一进程内多次检索只加载 BGE/FAISS 一次

## 注意事项

- 影响面对照前须先 `python main.py index-impact`；主库问答前须先 `python main.py index`
- 更换 embedding 模型后须删除对应 `data/faiss_index*` 并重建索引
- `data/faiss_index/`、`data/faiss_index_v12/`、`data/faiss_index_v13/` 已在 `.gitignore`，克隆后需本地建库
- 本仓库是演示数据，不是真审批
- DashScope 方案在 `indexer.py` / `rag.py` 中以注释保留，可切换回通义千问
