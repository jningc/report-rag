# 招标文件核对

投标人下载招标文件之后、动手写投标文件之前，用它把这份文件读一遍：列出废标条件、评分项、必须交的材料和格式里的空表，每条带页码；再拿 `company.yaml` 去对，标出缺什么。

不生成整本标书，不判断能不能中标。演示用政府采购网公开文件和虚构公司，不是真投标。

## 它解决什么

招标文件一百多页，「保证金」「资格」「业绩」在须知、评分、合同里都会出现。整份一起搜，容易把履约保证金当成投标保证金。本项目先切章，再只在该章里检索。

四步是固定工作流，不是聊天 Agent。模型只做三件事：切不准的章分类、从段落抽字段、对照 YAML 下结论。没有页码就标「人工看」，不猜。

## 怎么跑

环境：conda 环境 `report-rag`（Python 3.12）。

```bash
conda activate report-rag
pip install -r requirements.txt
```

下载三份公开招标 PDF（体积较大，不进 Git）：

```bash
# 命令见 sample/sources.md
```

核对：

```bash
python main.py check sample/beijing_road.pdf sample/company.yaml
```

提问（只在指定章节里搜）：

```bash
python main.py ask "投标保证金多少？" --pdf sample/beijing_road.pdf
python main.py ask "价格分：基准价 42 万，报价 45 万，满分 30" --pdf sample/beijing_road.pdf
```

界面：

```bash
streamlit run app.py
```

左侧是四张主表和时间、合同；点一行，右侧用原件页图按块坐标画框。可切换「解析文本」。没有页码的行不画框。

## 目录

```
main.py / app.py     入口：命令行核对、Streamlit 界面
tender/              核对主路径（解析 → 切章 → 按章检索 → 四步出表 → 提问）
  parse.py           按页抽文本和 bbox，渲页图
  sections.py        切章、用别名标类型
  index.py           按章建 BM25 + FAISS
  tables.py          四张表和辅助表的字段合同
  workflow.py        LangGraph 四步核对
  tools.py           search_section / follow_reference / read_company / calc_price_score
  ask_box.py         提问框，最多 5 步工具循环
  llm.py             对话模型客户端
sample/              虚构 company.yaml，样本 PDF 下载说明
docs/                方案、效果演示、笔记
archive/policy-impact/  旧的报销影响面 RAG（tag v-impact-baseline）
data/                运行时索引和上传缓存（不进 Git）
```

## 不做

扫描件 OCR、Word 招标文件、工程量清单、围串标、资质在线验真、自动写技术方案正文。

旧的报销制度影响面对照已移到 `archive/policy-impact/`，不再是主路径。
