"""hwdk.review — 硬件设计评审清单与测试报告生成

对应岗位职责：
  ② 确保符合电气规范、EMC/EMI 及可制造性（DFM）要求
  ③ 制定硬件测试方案，独立完成硬件单元测试、集成调试及系统联调
  ⑤ 编写并维护硬件设计文档、测试报告、BOM 清单及产品说明书
  ⑥ 参与硬件开发流程优化，推动设计标准化、模块化及经验沉淀

设计思路：把评审要点**清单化、可配置、可输出**，
使"设计评审"从口头讨论变成可归档的文档 —— 这正是设计标准化的落点。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ------------------------------------------------------------ 评审清单定义

@dataclass
class CheckItem:
    id: str
    category: str
    question: str
    severity: str = "major"     # critical / major / minor
    hint: str = ""


CHECKLIST: List[CheckItem] = [
    # ---- 电源 ----
    CheckItem("PWR-01", "电源", "每路电源的电压/电流余量是否 ≥ 30%？", "critical",
              "考虑满载、峰值与温升降额"),
    CheckItem("PWR-02", "电源", "LDO 结温是否核算过（Tj 留 20% 余量）？", "critical",
              "压差全部变热：P=(Vin−Vout)×Iout"),
    CheckItem("PWR-03", "电源", "上电时序与上下电斜率是否满足器件要求？", "major",
              "多路电源需确认先后顺序，避免闩锁"),
    CheckItem("PWR-04", "电源", "每个电源脚是否就近放置 100 nF 去耦？", "major"),
    CheckItem("PWR-05", "电源", "输入是否有反接保护、浪涌抑制与保险丝？", "major"),
    CheckItem("PWR-06", "电源", "DC-DC 电感饱和电流与输出电容纹波电流是否达标？", "major"),

    # ---- 信号链 ----
    CheckItem("SIG-01", "信号链", "运放的增益与带宽是否核算（含 GBW 限制）？", "major"),
    CheckItem("SIG-02", "信号链", "ADC 参考电压、LSB 与被测物理量的分辨率是否匹配需求？", "major"),
    CheckItem("SIG-03", "信号链", "抗混叠滤波截止频率是否低于奈奎斯特频率？", "critical",
              "fc 高于 fs/2 则抗混叠失效"),
    CheckItem("SIG-04", "信号链", "传感器激励、共模范围与失调漂移是否评估？", "major"),
    CheckItem("SIG-05", "信号链", "高阻节点是否有保护与屏蔽措施？", "minor"),

    # ---- 接口 ----
    CheckItem("IF-01", "接口", "I2C 上拉电阻是否按总线电容与上升时间计算？", "major"),
    CheckItem("IF-02", "接口", "UART 波特率误差是否 < 2~3%？", "major"),
    CheckItem("IF-03", "接口", "CAN 位定时采样点是否接近 87.5%，两端是否各 120 Ω？", "critical"),
    CheckItem("IF-04", "接口", "SPI 时钟频率是否留出建立/保持余量？", "major"),
    CheckItem("IF-05", "接口", "USB 差分阻抗与串联匹配电阻是否按要求？", "major"),
    CheckItem("IF-06", "接口", "对外接口是否有 ESD 保护与限流？", "major"),

    # ---- EMC/EMI ----
    CheckItem("EMC-01", "EMC/EMI", "开关电源环路面积是否最小化，输入是否有 π 型滤波？", "major"),
    CheckItem("EMC-02", "EMC/EMI", "高速信号是否有完整参考地平面与短回流路径？", "major"),
    CheckItem("EMC-03", "EMC/EMI", "晶振/时钟是否远离接口与板边，下方是否禁布线？", "major"),
    CheckItem("EMC-04", "EMC/EMI", "线缆与外壳的屏蔽/接地策略是否明确？", "major"),
    CheckItem("EMC-05", "EMC/EMI", "是否规划了辐射发射与传导发射的预测试？", "minor"),

    # ---- DFM/DFT ----
    CheckItem("DFM-01", "DFM", "最小线宽/线距/孔径是否满足所选工艺能力？", "critical"),
    CheckItem("DFM-02", "DFM", "元件间距是否留出手焊/返修空间？", "major"),
    CheckItem("DFM-03", "DFM", "封装与实物是否逐一核对（引脚号、极性、本体尺寸）？", "critical",
              "封装错是打样报废的头号原因"),
    CheckItem("DFM-04", "DFM", "丝印是否标注了极性、版本号与接口定义？", "minor"),
    CheckItem("DFT-01", "DFT", "关键电源轨是否预留测试点？", "major"),
    CheckItem("DFT-02", "DFT", "是否预留调试串口/调试口与复位按键？", "major"),
    CheckItem("DFT-03", "DFT", "是否预留固件烧录/升级接口？", "major"),

    # ---- 文档与流程 ----
    CheckItem("DOC-01", "文档", "BOM 是否通过位号重复/封装缺失/替代料校验？", "major"),
    CheckItem("DOC-02", "文档", "电源树与信号链是否有计算书可复核？", "major"),
    CheckItem("DOC-03", "文档", "接口定义与引脚分配表是否与固件一致？", "major"),
    CheckItem("DOC-04", "文档", "是否记录了本版改版点与遗留问题？", "major"),
]


@dataclass
class ReviewResult:
    answered: Dict[str, str] = field(default_factory=dict)   # id -> pass/fail/na/空
    notes: Dict[str, str] = field(default_factory=dict)

    def total(self) -> int:
        return len(CHECKLIST)


def evaluate_review(answers: Dict[str, str],
                    notes: Optional[Dict[str, str]] = None) -> dict:
    """按回答评估评审结果。

    answers: {check_id: 'pass'|'fail'|'na'}，未答视为未检查。
    """
    notes = notes or {}
    fails, unanswered = [], []
    for item in CHECKLIST:
        a = str(answers.get(item.id, "")).lower()
        if a == "fail":
            fails.append(item)
        elif a not in ("pass", "na"):
            unanswered.append(item)

    critical_fail = [i for i in fails if i.severity == "critical"]
    return {
        "total": len(CHECKLIST),
        "passed": sum(1 for i in CHECKLIST if str(answers.get(i.id, "")).lower() == "pass"),
        "failed": len(fails),
        "na": sum(1 for i in CHECKLIST if str(answers.get(i.id, "")).lower() == "na"),
        "unanswered": len(unanswered),
        "critical_failed": [
            {"id": i.id, "question": i.question, "hint": i.hint,
             "note": notes.get(i.id, "")} for i in critical_fail],
        "failed_items": [
            {"id": i.id, "category": i.category, "question": i.question,
             "severity": i.severity, "note": notes.get(i.id, "")} for i in fails],
        "ready": len(critical_fail) == 0 and len(unanswered) == 0,
    }


def render_checklist() -> str:
    """输出评审清单（Markdown），可直接作为设计评审表模板。"""
    L = ["# 硬件设计评审清单\n",
         f"共 {len(CHECKLIST)} 项，按类别分组；severity 为 critical 的项未通过则不建议投板。\n"]
    cats: Dict[str, List[CheckItem]] = {}
    for i in CHECKLIST:
        cats.setdefault(i.category, []).append(i)
    for cat, items in cats.items():
        L.append(f"## {cat}\n")
        L.append("| 编号 | 检查项 | 级别 | 结论 | 备注 |")
        L.append("|---|---|---|---|---|")
        for i in items:
            L.append(f"| {i.id} | {i.question} | {i.severity} | ☐ | |")
        L.append("")
    return "\n".join(L)


def render_review(result: dict) -> str:
    L = ["# 硬件设计评审结果\n"]
    L.append(f"- 检查项总数：{result['total']}")
    L.append(f"- 通过：{result['passed']}　未通过：{result['failed']}　"
             f"不适用：{result['na']}　未检查：{result['unanswered']}")
    L.append(f"- **是否具备投板条件：{'是' if result['ready'] else '否'}**\n")
    if result["critical_failed"]:
        L.append("## ❌ critical 未通过项（阻塞投板）\n")
        for i in result["critical_failed"]:
            L.append(f"- **{i['id']}** {i['question']}")
            if i["hint"]:
                L.append(f"    - 提示：{i['hint']}")
            if i["note"]:
                L.append(f"    - 备注：{i['note']}")
        L.append("")
    if result["failed_items"]:
        L.append("## 未通过项明细\n")
        L.append("| 编号 | 类别 | 级别 | 检查项 | 备注 |")
        L.append("|---|---|---|---|---|")
        for i in result["failed_items"]:
            L.append(f"| {i['id']} | {i['category']} | {i['severity']} | "
                     f"{i['question']} | {i['note']} |")
        L.append("")
    return "\n".join(L)


# ------------------------------------------------------------ 测试报告模板

POWER_ON_STEPS = [
    ("上电前目视检查", "确认无连锡/虚焊、极性器件方向、保险丝与跳线"),
    ("限流上电", "电源限流至额定 1.2 倍，观测输入电流是否异常"),
    ("静态电流测量", "空载测各路静态电流，与设计值比对"),
    ("电源轨电压", "逐路测量输出电压与纹波（示波器 AC 耦合，20 MHz 带宽限制）"),
    ("复位与时钟", "示波器确认复位时序与晶振起振（频率与幅值）"),
    ("烧录与识别", "烧录固件后确认芯片被识别、串口有启动打印"),
    ("接口回环", "逐项做接口回环/读写验证（UART 回显、I2C 扫描、SPI 读写、CAN 帧、USB 枚举）"),
    ("功能联调", "按测试用例逐项验证功能，记录实际结果与预期是否一致"),
    ("温升与长稳", "满载运行至热平衡，记录关键器件温度；持续运行观察是否异常复位"),
]


def render_test_plan(title: str, features: List[str],
                     interfaces: List[str]) -> str:
    """输出硬件测试方案（含上电检查表与接口测试项）。"""
    L = [f"# {title} · 硬件测试方案\n"]
    L.append("## 一、测试范围\n")
    for f in features:
        L.append(f"- {f}")
    L.append("")
    L.append("## 二、上电检查表\n")
    L.append("| # | 步骤 | 内容 | 预期 | 实测 | 结论 |")
    L.append("|---|---|---|---|---|---|")
    for idx, (name, desc) in enumerate(POWER_ON_STEPS, 1):
        L.append(f"| {idx} | {name} | {desc} | | | ☐ |")
    L.append("")
    L.append("## 三、接口测试项\n")
    L.append("| 接口 | 测试内容 | 仪器 | 预期 | 实测 | 结论 |")
    L.append("|---|---|---|---|---|---|")
    probe = {
        "I2C": "扫描地址、读写寄存器、观察上升时间与总线电容",
        "SPI": "读器件 ID、连续读写、观察 SCLK 波形与建立保持",
        "UART": "回环测试、误码统计、观察空闲电平与波特率误差",
        "CAN": "帧收发、总线仲裁、示波器看差分电平与位定时",
        "USB": "枚举、设备描述符、批量传输速率与稳定性",
    }
    for it in interfaces:
        L.append(f"| {it} | {probe.get(it, '按接口规范逐项验证')} | "
                 f"示波器 / 逻辑分析仪 | | | ☐ |")
    L.append("")
    L.append("## 四、记录要求\n")
    L.append("- 每个测试项都要记录**原始数据**（波形截图、实测值、时间），"
             "不允许只写\"正常\"")
    L.append("- 与预期不一致的项必须单独列出并跟踪到关闭")
    L.append("- 结论要能追溯到**测量条件**（温度、负载、电源电压、仪器型号与档位）")
    return "\n".join(L)


def render_test_report(title: str, model: str, date: str,
                       items: List[dict], notes: str = "") -> str:
    """把测试记录渲染成报告。

    items 每项：{step, expected, measured, instrument, conclusion, issue}
    conclusion ∈ pass / fail / na
    """
    n_pass = sum(1 for i in items if i.get("conclusion") == "pass")
    n_fail = sum(1 for i in items if i.get("conclusion") == "fail")
    L = [f"# {title} · 硬件测试报告\n"]
    L.append(f"- 样机型号：{model}")
    L.append(f"- 测试日期：{date}")
    L.append(f"- 测试项：{len(items)}　通过：{n_pass}　失败：{n_fail}　"
             f"通过率：{(n_pass / len(items) if items else 0):.1%}\n")
    L.append("## 一、测试记录\n")
    L.append("| # | 测试项 | 预期 | 实测 | 仪器 | 结论 |")
    L.append("|---|---|---|---|---|---|")
    for idx, it in enumerate(items, 1):
        mark = {"pass": "✅ pass", "fail": "❌ fail"}.get(
            str(it.get("conclusion", "")).lower(), "— na")
        L.append(f"| {idx} | {it.get('step', '')} | {it.get('expected', '')} | "
                 f"{it.get('measured', '')} | {it.get('instrument', '')} | {mark} |")
    L.append("")
    fails = [i for i in items if str(i.get("conclusion", "")).lower() == "fail"]
    L.append("## 二、问题与处理\n")
    if not fails:
        L.append("本次测试未发现失败项。\n")
    else:
        for idx, it in enumerate(fails, 1):
            L.append(f"### {idx}. {it.get('step', '')}\n")
            L.append(f"- 现象：{it.get('measured', '')}")
            L.append(f"- 预期：{it.get('expected', '')}")
            L.append(f"- 定位思路：{it.get('issue', '（待补充：先确认测量条件与焊接，再核对器件与设计值）')}")
            L.append("- 处理与结论：（待补充）\n")
    if notes:
        L.append("## 三、补充说明\n")
        L.append(notes)
        L.append("")
    return "\n".join(L)
