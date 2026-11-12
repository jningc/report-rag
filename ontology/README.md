# ontology/ · 招标文件核对本体

把「招标文件里可核对的东西」建模成类与属性，让抽取结果落在同一个结构上，评测时比对实例而不是自由文本。

**现状**：21 个类、12 个对象属性、8 个数据属性、21 条实例（取自 `sample/beijing_road.pdf`，页码逐条核过）。OWL 2 / Turtle，无推理机依赖。

```
tender.ttl      本体：类、属性、domain/range
instances.ttl   实例：一个项目、一个包、保证金、时间节点、两类判定
```

## 为什么要有它

`tender/tables.py` 里六张表是**输出格式**，本体是**语义**。两者不重复：

| 表里的字段 | 本体里是什么 |
|---|---|
| `FeibiaoRow.condition` | `tl:DisqualificationCondition` 实例 |
| `Ref(page=17)` | `tl:PageReference` 实例 + `tl:pageNumber` |
| `verdict="人工看"` | `tl:Verdict` 实例，`hasEvidence` 为空 |

好处是判定可校验：一条 `tl:Verdict` 若没有 `hasEvidence`，或证据里的 `PageReference` 没页码，按规则就该降级成「人工看」。这条约束写在类注释里，将来可以用 SHACL 自动查。

## 校验

```bash
pip install rdflib
python ontology/check.py
```

`check.py` 只做三件事：能否解析、类/属性/实例计数、有没有用了没定义的类或漏 domain/range 的属性。

## 边界

- **不做推理**：没有引入 reasoning，`subClassOf` 只用于文档语义，不指望它推导出结论。
- **不替代规则**：页数、金额这类可计算的，仍然走代码（`calc_price_score` 一类），本体只存结果。
- **实例不是语料**：`instances.ttl` 是给结构做样板，不是训练数据。
