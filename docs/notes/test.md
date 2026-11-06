# 项目怎么测

在仓库根目录、已激活的 `report-rag` conda 环境里执行。不要用 `python tests/xxx.py` 直接跑测试文件。

## 1. 不调 API（改代码后先跑这个）

对照层：短结论解析、漏报/误报、检索 / schema / 翻转分层、离线重放。

```bash
python -m pytest tests/ -v
```

应看到 24 passed。失败时终端会打印断言和对照的旧/新短结论。

## 2. 检索层评测（不调 LLM，需要主库）

```bash
python main.py index
python main.py eval
```

测 `data/eval_cases.json` 的 source 命中和拒答阈值。索引在 `data/faiss_index/`。

## 3. 影响面对照

先建旧/新报销库（只需一次，换 PDF 或切分参数后再建）：

```bash
python main.py index-impact
```

打模型（要 `.env` 里的 `DEVAGI_API_KEY`），结果写入 `data/impact_last.json`：

```bash
python main.py impact
```

不打模型，用已有 JSON 重算三层分数（改 `parse_short_conclusion` / `score_row` 后用这个）：

```bash
python main.py impact --offline
```

结尾看三行，不要只看一个对齐率：

- 检索 m/12：出处是否落到对应报销稿
- schema n/12：第一行是否五种结论（可报上限必须有数字）
- 翻转 p/n：仅 schema 过的题，字段变没变是否等于 `should_flip`；schema 不过标「未评」

没有 `impact_last.json` 时 `--offline` 会报错，先跑一次在线 `impact`。

## 4. 单题问答（可选，要 Key）

```bash
python main.py ask "上海出差住了600一晚，能报多少？" -k 3
```

影响面用的是 v12/v13 两个库；这条默认打主库 `data/faiss_index/`。指定库：

```bash
python main.py ask "上海出差住了600一晚，能报多少？" --index-dir data/faiss_index_v13
```

## 5. 界面

索引和 `.env` 配好后：

```bash
streamlit run app.py
```

第一屏对照表；点「运行对照」等于在线 `impact`。改完解析规则可先终端 `--offline`，再刷新页面看 `impact_last.json`。

## 建议顺序

1. `python -m pytest tests/ -v`
2. 有主库则 `python main.py eval`
3. 有 `impact_last.json` 则 `python main.py impact --offline`
4. 需要新生成答案时再 `python main.py impact`
