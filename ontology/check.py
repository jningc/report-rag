"""本体自检：解析、计数、类完整性。用法: python ontology/check.py

需要 rdflib（不在主依赖里，只跑这个脚本时装）。
"""

import sys
from collections import Counter
from pathlib import Path

try:
    from rdflib import OWL, RDF, RDFS, Graph, URIRef
except ImportError:
    sys.exit("缺 rdflib：pip install rdflib")

HERE = Path(__file__).resolve().parent


def main() -> int:
    g = Graph()
    for name in ("tender.ttl", "instances.ttl"):
        g.parse(HERE / name, format="turtle")

    classes = set(g.subjects(RDF.type, OWL.Class))
    oprops = set(g.subjects(RDF.type, OWL.ObjectProperty))
    dprops = set(g.subjects(RDF.type, OWL.DatatypeProperty))
    individuals = {
        s for s in g.subjects(RDF.type, None)
        if isinstance(s, URIRef) and s not in classes | oprops | dprops
        and g.value(s, RDF.type) not in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.Ontology)
    }

    print(f"三元组 {len(g)}")
    print(f"类 {len(classes)} · 对象属性 {len(oprops)} · 数据属性 {len(dprops)} · 实例 {len(individuals)}")

    bad_props = [str(p).rsplit("#", 1)[-1] for p in oprops
                 if g.value(p, RDFS.domain) is None or g.value(p, RDFS.range) is None]
    used = {g.value(s, RDF.type) for s in individuals}
    undef = [str(u).rsplit("#", 1)[-1] for u in used - classes]

    print("缺 domain/range 的对象属性:", bad_props or "无")
    print("未定义的类:", undef or "无")
    print("实例分布:", dict(Counter(str(g.value(s, RDF.type)).rsplit("#", 1)[-1]
                                 for s in individuals).most_common()))

    errors = len(bad_props) + len(undef)
    print("\n结果:", "通过" if errors == 0 else f"失败（{errors} 处）")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
