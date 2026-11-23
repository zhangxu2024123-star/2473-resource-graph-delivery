#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资源图谱样例校验器（只读）。

用法：
    python verify.py --nodes data/nodes.json --edges data/edges.json --schema-dir schema
    python verify.py --self-test

退出码：0 = 全部通过；1 = 有失败项。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    sys.exit("缺少依赖 jsonschema，请先执行：pip install -r requirements.txt")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NODE_TYPES = ["company", "contact", "industry_tag", "capability", "demand",
              "event", "opportunity", "expert", "site", "policy"]
EDGE_TYPES = ["works_at", "provides", "needs", "attended", "introduced",
              "partnered", "tagged_with", "involved_in", "suggested_match", "similar_to"]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _dialect_tag(uri: str) -> str:
    """从 $schema URI 里取出版本号，如 .../draft/2020-12/schema -> 2020-12。"""
    parts = [p for p in uri.split("/") if p and p != "schema"]
    return parts[-1] if parts else "unknown"


def build_validator(schema_path: Path):
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema), schema.get("$schema", "")


def first_errors(validator, items):
    """返回 [(index, item_id, [错误消息...])]，每个元素只保留前 3 条错误。"""
    problems = []
    for idx, item in enumerate(items):
        errs = sorted(validator.iter_errors(item), key=lambda e: list(e.absolute_path))
        if errs:
            msgs = []
            for err in errs[:3]:
                where = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path)
                msgs.append(f"{where}: {err.message}")
            item_id = item.get("id", f"#{idx}") if isinstance(item, dict) else f"#{idx}"
            problems.append((idx, item_id, msgs))
    return problems


def check_integrity(nodes, edges):
    """Schema 管形态，这里管引用完整性：端点存在、同集团、可见性不越界。"""
    issues = []
    by_id = {n["id"]: n for n in nodes}
    for e in edges:
        for side in ("source_id", "target_id"):
            if e[side] not in by_id:
                issues.append(f"{e['id']}: {side}={e[side]} 在 nodes.json 中不存在")
        src, tgt = by_id.get(e["source_id"]), by_id.get(e["target_id"])
        if src and tgt:
            for node in (src, tgt):
                if node["org_id"] != e["org_id"]:
                    issues.append(f"{e['id']}: 与节点 {node['id']} 的 org_id 不一致（跨集团边）")
            # 可见性继承：边不得比任一端点更宽（private > site > org）
            rank = {"private": 0, "site": 1, "org": 2}
            strictest = min(rank[src["visibility"]], rank[tgt["visibility"]])
            if rank[e["visibility"]] > strictest:
                issues.append(
                    f"{e['id']}: visibility={e['visibility']} 宽于端点 {src['id']}({src['visibility']})"
                    f"/{tgt['id']}({tgt['visibility']})，应按更严一侧继承"
                )
    return issues


def check_invariants(nodes, edges):
    """Schema 与跨对象一致性都查不到的节点级不变量：时间顺序、同类型相似、节点内引用存在。"""
    issues = []
    by_id = {n["id"]: n for n in nodes}
    tagged = {}
    for e in edges:
        if e["edge_type"] == "tagged_with":
            tagged.setdefault(e["source_id"], set()).add(e["target_id"])
    for n in nodes:
        if n["node_type"] == "company":
            arr = set(n.get("industry_tag_ids") or [])
            if arr != tagged.get(n["id"], set()):
                issues.append(
                    f"{n['id']}: industry_tag_ids={sorted(arr)} 与 tagged_with 边={sorted(tagged.get(n['id'], set()))} 不一致"
                    "（数组是边的派生索引，必须与边同步）"
                )
    for e in edges:
        if e["edge_type"] == "similar_to":
            src, tgt = by_id.get(e["source_id"]), by_id.get(e["target_id"])
            if src and tgt and src["node_type"] != tgt["node_type"]:
                issues.append(
                    f"{e['id']}: similar_to 两端类型不同（{src['node_type']} → {tgt['node_type']}），"
                    "该关系只允许同类型节点之间"
                )
    for n in nodes:
        if n.get("starts_at") and n.get("ends_at") and n["ends_at"] <= n["starts_at"]:
            issues.append(f"{n['id']}: ends_at({n['ends_at']}) 未晚于 starts_at({n['starts_at']})")
        refs = []
        if n.get("primary_company_id"):
            refs.append(("primary_company_id", n["primary_company_id"]))
        for tid in n.get("industry_tag_ids") or []:
            refs.append(("industry_tag_ids", tid))
        for field, ref in refs:
            if ref not in by_id:
                issues.append(f"{n['id']}: {field}={ref} 在 nodes.json 中不存在")
        if n["visibility"] == "site" and not n.get("site_id"):
            issues.append(f"{n['id']}: visibility=site 但 site_id 为空")
    return issues


def run_validate(args) -> int:
    schema_dir = Path(args.schema_dir)
    node_schema_path = schema_dir / "node.schema.json"
    edge_schema_path = schema_dir / "edge.schema.json"
    node_validator, node_dialect = build_validator(node_schema_path)
    edge_validator, edge_dialect = build_validator(edge_schema_path)
    node_tag = _dialect_tag(node_dialect)
    edge_tag = _dialect_tag(edge_dialect)
    print(f"loaded schema: node.schema.json ({node_tag}), edge.schema.json ({edge_tag})")

    nodes = load_json(Path(args.nodes))
    edges = load_json(Path(args.edges))
    ok = True

    node_errors = first_errors(node_validator, nodes)
    print(f"validating {Path(args.nodes).name} ... {len(nodes) - len(node_errors)}/{len(nodes)} valid")
    if node_errors:
        ok = False
        for _idx, item_id, msgs in node_errors:
            print(f"  FAIL node {item_id}")
            for msg in msgs:
                print(f"    - {msg}")

    edge_errors = first_errors(edge_validator, edges)
    print(f"validating {Path(args.edges).name} ... {len(edges) - len(edge_errors)}/{len(edges)} valid")
    if edge_errors:
        ok = False
        for _idx, item_id, msgs in edge_errors:
            print(f"  FAIL edge {item_id}")
            for msg in msgs:
                print(f"    - {msg}")

    ntc = Counter(n["node_type"] for n in nodes)
    etc = Counter(e["edge_type"] for e in edges)
    oc = Counter(e["origin"] for e in edges)
    print(
        f"coverage: node_type {len([t for t in NODE_TYPES if ntc.get(t)])}/{len(NODE_TYPES)}, "
        f"edge_type {len([t for t in EDGE_TYPES if etc.get(t)])}/{len(EDGE_TYPES)}, "
        f"origin {{human:{oc.get('human', 0)}, rule:{oc.get('rule', 0)}, ai:{oc.get('ai', 0)}}}"
    )
    per_node = ", ".join(f"{t}:{ntc.get(t, 0)}" for t in NODE_TYPES)
    per_edge = ", ".join(f"{t}:{etc.get(t, 0)}" for t in EDGE_TYPES)
    print(f"node_type detail: {per_node}")
    print(f"edge_type detail: {per_edge}")

    sc = Counter(n["source_state"] for n in nodes)
    print(f"source coverage: phase1 {sc.get('phase1', 0)} / new_collection {sc.get('new_collection', 0)}")
    ai_pending = [e for e in edges if e["origin"] == "ai" and e.get("review_status") == "pending"]
    ai_leak = [e["id"] for e in edges if e["origin"] == "ai" and e["visibility"] != "private"]
    print(f"ai review queue: {len(ai_pending)} pending, member-visible ai edges: {len(ai_leak)}")

    integrity = check_integrity(nodes, edges)
    print(f"referential integrity: {len(edges) - len({i.split(':')[0] for i in integrity})}/{len(edges)} edges resolved")
    for issue in integrity:
        ok = False
        print(f"  FAIL {issue}")

    for issue in check_invariants(nodes, edges):
        ok = False
        print(f"  FAIL {issue}")

    print("RESULT: PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


BAD_EDGES = {
    "bad_1_missing_edge_type.json": {
        "id": "e_901", "org_id": "org_demo01", "source_id": "contact_001", "target_id": "company_001",
        "weight": 0.8,
        "evidence_ref": {"source_table": "crm_contact", "source_id": "ct_1001"},
        "confidence": 0.9, "origin": "human", "valid_from": "2026-01-01T00:00:00+08:00",
        "valid_to": None, "visibility": "org",
    },
    "bad_2_weight_out_of_range.json": {
        "id": "e_902", "org_id": "org_demo01", "source_id": "contact_001", "target_id": "company_001",
        "edge_type": "works_at", "weight": 1.5,
        "evidence_ref": {"source_table": "crm_contact", "source_id": "ct_1001"},
        "confidence": 0.9, "origin": "human", "valid_from": "2026-01-01T00:00:00+08:00",
        "valid_to": None, "visibility": "org",
    },
    "bad_3_ai_edge_visible_to_member.json": {
        "id": "e_903", "org_id": "org_demo01", "source_id": "capability_001", "target_id": "demand_001",
        "edge_type": "suggested_match", "weight": 0.72,
        "evidence_ref": {"source_table": "ai_match_run", "source_id": "run_20261120_01"},
        "confidence": 0.66, "origin": "ai", "valid_from": "2026-11-20T02:10:00+08:00",
        "valid_to": None, "visibility": "org", "review_status": "pending", "reviewed_by": None,
    },
    "bad_4_amount_field.json": {
        "id": "e_904", "org_id": "org_demo01", "source_id": "company_001", "target_id": "opportunity_001",
        "edge_type": "involved_in", "weight": 0.8,
        "evidence_ref": {"source_table": "crm_opportunity", "source_id": "op_2001"},
        "confidence": 0.9, "origin": "human", "valid_from": "2026-11-01T00:00:00+08:00",
        "valid_to": None, "visibility": "org", "amount": 12000000,
    },
}


def run_self_test(args) -> int:
    schema_path = Path(args.schema_dir) / "edge.schema.json"
    validator, _ = build_validator(schema_path)
    rejected = 0
    for name, bad in BAD_EDGES.items():
        errs = sorted(validator.iter_errors(bad), key=lambda e: list(e.absolute_path))
        if errs:
            rejected += 1
            err = errs[0]
            where = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path)
            print(f"  rejected {name}: {where}: {err.message}")
        else:
            print(f"  NOT REJECTED {name} —— 校验器存在漏洞，请检查 Schema")
    total = len(BAD_EDGES)
    print(f"{rejected}/{total} correctly rejected")
    ok = rejected == total
    print("RESULT: PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="资源图谱节点/关系样例校验器（只读）")
    parser.add_argument("--nodes", default="data/nodes.json", help="节点样例文件")
    parser.add_argument("--edges", default="data/edges.json", help="关系样例文件")
    parser.add_argument("--schema-dir", default="schema", help="Schema 目录")
    parser.add_argument("--self-test", action="store_true", help="用 3 个坏样例验证校验器本身有效")
    args = parser.parse_args()

    print(f"python {sys.version.split()[0]} / jsonschema {_version()}")
    return run_self_test(args) if args.self_test else run_validate(args)


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("jsonschema")
    except Exception:  # pragma: no cover
        return getattr(jsonschema, "__version__", "unknown")


if __name__ == "__main__":
    raise SystemExit(main())
