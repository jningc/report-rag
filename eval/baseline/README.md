# v1 基线（2026-11-10 冻结）

改造前的回滚点和对比基准。**不要覆盖**：v2 的数字一律另存，基线只在「确认要重冻」时重跑。

## 怎么来的

```bash
env -u PYTHONPATH ~/miniforge3/envs/report-rag/bin/python eval/freeze_baseline.py
# 只补某一份（其余文档的 meta 会保留）
env -u PYTHONPATH ~/miniforge3/envs/report-rag/bin/python eval/freeze_baseline.py --docs chongzuo_green
```

**每份 PDF 配自己的公司**，脚本里写死成对：

| 招标文件 | 公司文件 |
|---|---|
| `sample/beijing_road.pdf` | `sample/beijing_road_company.yaml`（监理公司，总监专业不符、保证金未备） |
| `sample/chongzuo_green.pdf` | `sample/chongzuo_green_company.yaml`（造林公司，缺市政公用施工总承包） |
| `sample/wenling_video.pdf` | `sample/wenling_video_company.yaml`（视频接入公司，项目经理土木专业、无类似业绩） |

`meta.json` 里记 `company` 与 `company_sha256`：**公司文件一改就等于换题，旧分数不能再比**。

页码口径：一律用 **PDF 物理页**（第 1 页=封面）。页脚的印刷页码与物理页不一致——beijing、chongzuo 差 2（物理 p8 → 页脚 6），wenling 一致。题集的 `expect_pages`、`refs.page`、界面引用都是物理页。

每份文档落四份产物：

| 文件 | 内容 |
|---|---|
| `check.txt` | `render_tables` 的文本，`compare.py` 直接吃 |
| `tables.json` | 六张表的原始数据（含 refs 的 page/bbox），逐条 diff 用这个 |
| `sections.json` | 切章结果，改造后章节必须能对上 |
| `meta.json` | 页数、章数、条数、耗时、git 提交、模型 |

`summary.json` 是汇总，附 `compare.py` 的正例/负例得分（明细在每份文档的 `compare.json`）。

打分用 `tables.json` 而不是渲染后的 `check.txt`：渲染会丢字段（评分表的 `standard` 不打印），文本打分摸不到「评标基准价」这类只存在于字段里的内容。

引擎：v1（`tender/workflow.py` 五节点直排），模型 `deepseek-chat`，embedding `BAAI/bge-small-zh-v1.5`（CPU）。

## 一组数字

| 文档 | 页 | 章 | 废标 | 评分 | 材料 | 空位 | 时间 | 合同 | 行数 | refs | bbox 空 | ★ 行 | 正例 | 负例 | 判定断言 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| beijing_road | 92 | 7 | 13 | 9 | 11 | 5 | 10 | 12 | 60 | 96 | 21（22%） | 0 | 6/8 | 1/1 | 7 |
| chongzuo_green | 105 | 6 | 20 | 4 | 14 | 59 | 11 | 7 | 115 | 133 | 59（44%） | 1 | 3/5 | 0/1 | 2 |
| wenling_video | 64 | 6 | 22 | 12 | 17 | 38 | 13 | 11 | 113 | 137 | 38（28%） | 1 | 5/5 | 1/1 | 3 |

> 2026-11-11 全部重冻：**每份 PDF 配自己的公司文件**（meta 里记 `company` 与 `company_sha256`）。beijing 复用索引（`cached-index`），chongzuo、wenling 首次建库（`full-parse`）。
> 行数与 refs 不止「小幅」漂。同一份 beijing，换索引/重跑，空位表 5↔37 条、refs 96↔137、总行数 60↔92，**分数一分没变**。所以门禁只能看分数和 ★ 对账，行数连「变化告警」都不能当。

题集合计 21 条（正例 18 / 负例 3，其中 12 条断言判定值）→ v1 正例 14/18，负例 2/3。无页码行 0。

判定断言从 5 条扩到 12 条后，beijing 从 7/8 掉到 6/8：`bj-cap` 页码命中 p8、但判成「人工看」，而公司报价 45 万在 47.13 万限价内，应为「满足」。这条以前因为没断言判定值而被算作通过。

逐题明细：

- beijing_road：`bj-decrypt` 页码错（期望 p8 的解密时间 30 分钟，实际给 p4/6/10/16/19）；`bj-cap` 判定不符（实际「人工看」，应为「满足」——报价 45 万 < 最高限价 47.13 万）。7 条判定断言里 6 条判对
- chongzuo_green：`cz-bond`、`cz-cap` 两条未抽到——换成本行业的造林公司后，「本项目不收取投标保证金」和「超最高限价即无效」都没进废标/材料表；`cz-neg-perf-bond` **违规**——履约保证金（p26 前附表 35）混进了废标表
- wenling_video：5 条正例全过（含 3 条判定断言：不收保证金→无须提供、报价在预算内→满足、有效期满 90 天→人工看），负例也干净

耗时：60 / 68 / 66 秒。章缺失：chongzuo 与 wenling 都没有独立的「资格审查」章（`missing_sections`）。

## ★/▲ 对账（`eval/markers.json`）

原文标记数从 PDF 文本层数出来，和废标表 `star=True` 的行数对账。v1 的结果是**标记基本没进表**：

| 文档 | 原文标记 | 标记页 | star=True 行 | 覆盖标记页 |
|---|---|---|---|---|
| beijing_road | 2（★2，是 p26 的「★号条款响应」审查项） | 26 | 0 | 0/1 |
| chongzuo_green | 30（★22、▲8） | 9,16,19,20,21,28,32,44,82,85 | 1 | 1/10 |
| wenling_video | 10（▲10） | 10,11,16,30,33 | 1 | 1/5 |

原因在代码里：★ 只在废标节点的检索范围（邀请/须知/资格）里找，且命中一条就 `break`；模型自己填的 `star` 字段又没人校验（wenling 的上一次跑出过 5 行，这次只剩 1 行，同一份文件都能变）。这项不进分数，是独立指标——v2 要把「行数可比、标记页能指到」做出来。

## 基线自己就带着的缺口

这些是 v2 要改善、至少不能退化的点，改造前先记在这里，免得改完说不清是变好还是变坏。

1. **★ 条款没进废标表**。原文 2 / 30 / 10 个标记，废标表只有 0 / 1 / 1 行，覆盖标记页 0/1、1/10、1/5。而且 beijing 的 ★ 是 p26「★号条款响应」这个审查项——说明按字符判 ★ 必错，得逐条认定语义。
2. **能用的 bbox 只有三成**。refs 里 22% / 44% / 28% 完全没有坐标；剩下有坐标的里，beijing 40/75、wenling 42/99 是「整页高」的框（高度 >500pt），画出来就是盖住整页。按 refs 算，能定位到条款级的：beijing 35/96（36%）、chongzuo 39/133（29%）、wenling 57/137（42%）。未来校验段「按 bbox 回查原文」就卡在这个覆盖率上。
3. **串表与漏表都还在**。履约保证金（合同阶段）仍在 chongzuo 废标表里；「本项目不收取投标保证金」这种「结论是空」的条款，chongzuo 没进表、wenling 进了（p5）；「超最高限价即无效」chongzuo 没进废标表。

题集本身的历史：旧 8 条（全在 beijing_road、页码无原文依据、keyword 取「组成」这类虚词、无法表达负例）已全部作废；现在 21 条，附原文摘录、5 条断言判定值，人工复核清单在 `eval/题集核对清单.md`。

## 判读基线时注意

- 同一份 PDF 重跑，`deepseek-chat` 温度 0 也不保证逐字一致；所以 diff 要按「条目内容」比，不按行号比。
- 行数不是越多越好，也不稳。空位表在 chongzuo 是 59 行、beijing 只有 5 行，里面都混着重复的空表头；v2 合并后行数会掉，这是变好。
- `verdict` 只有废标/材料两张表有，评分/空位/时间/合同没有判定，统计时别把它们算进分母。
