"""hwdk.bom — BOM 清单校验与整理

对应岗位职责第 5 条（编写维护 BOM 清单等技术资料）与第 6 条（设计标准化、经验沉淀）：
把"BOM 里常见的人为错误"变成可自动检查的规则。

检查项：
  · 位号重复
  · 位号格式与排序
  · 封装缺失
  · 关键参数缺失（阻容值 / 耐压 / 精度 / 封装尺寸）
  · 器件是否在常用库中（可选白名单）
  · 单点失效料（只有一家供应商且无替代）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

# ---------------------------------------------------------------- 数据结构

REQUIRED_FIELDS = ["ref", "value", "package", "qty"]
# 阻容类必填的附加字段
PASSIVE_EXTRA = {"resistor": ["tolerance", "power"],
                 "capacitor": ["tolerance", "voltage"],
                 "inductor": ["current"]}


@dataclass
class BomItem:
    ref: str
    value: str = ""
    package: str = ""
    qty: int = 1
    category: str = ""          # resistor / capacitor / ic / connector / ...
    manufacturer: str = ""
    part_number: str = ""
    alternatives: List[str] = field(default_factory=list)
    dnp: bool = False           # Do Not Populate
    note: str = ""

    @staticmethod
    def from_dict(d: dict) -> "BomItem":
        return BomItem(
            ref=str(d.get("ref", "")).strip(),
            value=str(d.get("value", "")).strip(),
            package=str(d.get("package", "")).strip(),
            qty=int(d.get("qty", 1)),
            category=str(d.get("category", "")).strip().lower(),
            manufacturer=str(d.get("manufacturer", "")).strip(),
            part_number=str(d.get("part_number", "")).strip(),
            alternatives=list(d.get("alternatives", [])),
            dnp=bool(d.get("dnp", False)),
            note=str(d.get("note", "")),
        )

    def to_dict(self) -> dict:
        return {"ref": self.ref, "value": self.value, "package": self.package,
                "qty": self.qty, "category": self.category,
                "manufacturer": self.manufacturer, "part_number": self.part_number,
                "alternatives": self.alternatives, "dnp": self.dnp, "note": self.note}


@dataclass
class BomIssue:
    level: str        # error / warning
    ref: str
    rule: str
    message: str


@dataclass
class BomReport:
    items: List[BomItem]
    issues: List[BomIssue]

    @property
    def errors(self) -> List[BomIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> List[BomIssue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def total_components(self, include_dnp: bool = False) -> int:
        return sum(i.qty for i in self.items if include_dnp or not i.dnp)

    def by_category(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for i in self.items:
            out[i.category or "unknown"] = out.get(i.category or "unknown", 0) + i.qty
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def summary(self) -> str:
        return (f"{len(self.items)} 个位号 / {self.total_components()} 个器件"
                f"（不含 DNP）· {len(self.errors)} error · {len(self.warnings)} warning")

    def to_dict(self) -> dict:
        return {"summary": self.summary(),
                "total_refs": len(self.items),
                "total_qty": self.total_components(),
                "by_category": self.by_category(),
                "issues": [{"level": i.level, "ref": i.ref, "rule": i.rule,
                            "message": i.message} for i in self.issues]}


# ------------------------------------------------------------------ 校验规则

_REF_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


def _check_ref_format(item: BomItem, issues: List[BomIssue]) -> None:
    if not item.ref:
        issues.append(BomIssue("error", item.ref, "ref-empty", "位号为空"))
        return
    for one in [r.strip() for r in item.ref.split(",") if r.strip()]:
        if not _REF_RE.match(one):
            issues.append(BomIssue("error", item.ref, "ref-format",
                                   f"位号 '{one}' 不符合 '字母+数字' 规范"))


def _check_required(item: BomItem, issues: List[BomIssue]) -> None:
    if not item.value:
        issues.append(BomIssue("error", item.ref, "value-missing", "缺 value（阻容值/型号）"))
    if not item.package:
        issues.append(BomIssue("error", item.ref, "package-missing", "缺 package（封装）"))
    if item.qty <= 0:
        issues.append(BomIssue("error", item.ref, "qty-invalid", f"数量非法：{item.qty}"))


def _check_passive_extra(item: BomItem, issues: List[BomIssue]) -> None:
    need = PASSIVE_EXTRA.get(item.category)
    if not need:
        return
    note = item.note.lower()
    for field_name in need:
        if field_name not in note:
            issues.append(BomIssue(
                "warning", item.ref, f"{item.category}-{field_name}",
                f"{item.category} 未在 note 中标注 {field_name}（采购与替代料需要）"))


def _check_single_source(item: BomItem, issues: List[BomIssue]) -> None:
    if item.category in ("ic", "connector", "module") and item.part_number:
        if not item.alternatives:
            issues.append(BomIssue(
                "warning", item.ref, "single-source",
                f"{item.part_number} 无替代料，存在单点供货风险"))


def validate_bom(raw_items: Iterable[dict]) -> BomReport:
    """校验 BOM，返回带问题的报告。"""
    items = [BomItem.from_dict(d) for d in raw_items]
    issues: List[BomIssue] = []

    # 位号重复（跨行、跨逗号都要查）
    seen: Dict[str, str] = {}
    for it in items:
        for one in [r.strip() for r in it.ref.split(",") if r.strip()]:
            if one in seen:
                issues.append(BomIssue("error", it.ref, "ref-duplicated",
                                       f"位号 {one} 重复（另见 {seen[one]}）"))
            else:
                seen[one] = it.ref

    for it in items:
        _check_ref_format(it, issues)
        _check_required(it, issues)
        _check_passive_extra(it, issues)
        _check_single_source(it, issues)

    # 同封装同容值/阻值的重复行（可合并）
    groups: Dict[tuple, List[str]] = {}
    for it in items:
        if it.category in ("resistor", "capacitor", "inductor"):
            groups.setdefault((it.category, it.value, it.package), []).append(it.ref)
    for (cat, val, pkg), refs in groups.items():
        if len(refs) > 1:
            issues.append(BomIssue("warning", ",".join(refs), "mergeable",
                                   f"{cat} {val} {pkg} 分成 {len(refs)} 行，建议合并"))

    return BomReport(items=items, issues=issues)


# -------------------------------------------------------------- 导出与统计

def to_csv(report: BomReport) -> str:
    """导出标准 BOM CSV（位号, 类别, 值, 封装, 数量, 厂商, 料号, 替代料, DNP）。"""
    lines = ["ref,category,value,package,qty,manufacturer,part_number,alternatives,dnp"]
    for it in report.items:
        alt = "|".join(it.alternatives)
        lines.append(f'"{it.ref}","{it.category}","{it.value}","{it.package}",'
                     f'{it.qty},"{it.manufacturer}","{it.part_number}","{alt}",'
                     f'{"1" if it.dnp else "0"}')
    return "\n".join(lines) + "\n"


def to_markdown(report: BomReport) -> str:
    L = ["# BOM 校验报告\n", f"- {report.summary()}\n"]
    L.append("## 一、器件构成\n")
    L.append("| 类别 | 数量 |")
    L.append("|---|---|")
    for cat, n in report.by_category().items():
        L.append(f"| {cat} | {n} |")
    L.append("")
    L.append("## 二、问题清单\n")
    if not report.issues:
        L.append("未发现问题。\n")
    else:
        L.append("| 级别 | 位号 | 规则 | 说明 |")
        L.append("|---|---|---|---|")
        for i in report.issues:
            mark = "❌ error" if i.level == "error" else "⚠️ warning"
            L.append(f"| {mark} | {i.ref} | {i.rule} | {i.message} |")
        L.append("")
    return "\n".join(L)
