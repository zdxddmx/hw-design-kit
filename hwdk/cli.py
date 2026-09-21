"""hwdk.cli — 命令行入口

    python -m hwdk calc ldo    --vin 24 --vout 5 --iout 1.0
    python -m hwdk calc i2c    --vdd 3.3 --cbus 200 --tr 300
    python -m hwdk calc uart   --fsys 168000000 --baud 115200
    python -m hwdk calc can    --fclock 42000000 --bitrate 500000
    python -m hwdk calc adc    --vref 3.3 --bits 12 --full-scale 10 --span 10
    python -m hwdk bom  bom.json -o bom_report.md
    python -m hwdk checklist  -o checklist.md
    python -m hwdk testplan --title "XX 主控板" -o testplan.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import bom as bom_mod
from . import calc as calc_mod
from . import review as review_mod


def _print_result(r: calc_mod.CalcResult) -> None:
    print(f"== {r.name} ==")
    for s in r.steps:
        print(f"  · {s}")
    for w in r.warnings:
        print(f"  ⚠ {w}")
    print(f"  结论: {r.summary}")
    print(f"  判定: {'通过' if r.ok else '不通过'}")
    print()


def cmd_calc(args: argparse.Namespace) -> int:
    k = args.kind
    if k == "ldo":
        r = calc_mod.ldo_power(args.vin, args.vout, args.iout,
                               theta_ja=args.theta, t_ambient=args.tamb)
    elif k == "dcdc":
        r = calc_mod.dcdc_power(args.vin, args.vout, args.iout, args.eff)
    elif k == "adc":
        r = calc_mod.adc_resolution(args.vref, args.bits, args.full_scale, args.span)
    elif k == "aa":
        r = calc_mod.antialias_filter(args.r, args.c, args.fsignal, args.fsample)
    elif k == "i2c":
        r = calc_mod.i2c_pullup(args.vdd, args.cbus, args.tr)
    elif k == "uart":
        r = calc_mod.uart_baud_error(args.fsys, args.baud, args.oversampling)
    elif k == "can":
        r = calc_mod.can_bit_timing(args.fclock, args.bitrate, args.sample_point)
    elif k == "can-term":
        r = calc_mod.can_termination(args.nodes, args.stub, args.bitrate / 1000.0)
    elif k == "spi":
        r = calc_mod.spi_max_clock(args.tsu, args.thold, args.tprop)
    elif k == "usb":
        r = calc_mod.usb_series_resistor(args.speed)
    else:
        print(f"未知计算类型: {k}", file=sys.stderr)
        return 2
    _print_result(r)
    if args.json:
        Path(args.json).write_text(
            json.dumps(r.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON 已写入 {args.json}")
    return 0 if r.ok else 1


def cmd_bom(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("items", data.get("bom", []))
    rep = bom_mod.validate_bom(data)
    print(rep.summary())
    for cat, n in rep.by_category().items():
        print(f"  {cat:<12} {n}")
    print()
    for i in rep.issues:
        mark = "❌" if i.level == "error" else "⚠️"
        print(f"  {mark} [{i.rule}] {i.ref}: {i.message}")
    if args.out:
        Path(args.out).write_text(bom_mod.to_markdown(rep), encoding="utf-8")
        print(f"\n报告已写入 {args.out}")
    if args.csv:
        Path(args.csv).write_text(bom_mod.to_csv(rep), encoding="utf-8")
        print(f"CSV 已写入 {args.csv}")
    return 0 if rep.ok else 1


def cmd_checklist(args: argparse.Namespace) -> int:
    md = review_mod.render_checklist()
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"清单已写入 {args.out}（共 {len(review_mod.CHECKLIST)} 项）")
    else:
        print(md)
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    res = review_mod.evaluate_review(data.get("answers", {}), data.get("notes", {}))
    md = review_mod.render_review(res)
    print(md)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"\n评审结果已写入 {args.out}")
    return 0 if res["ready"] else 1


def cmd_testplan(args: argparse.Namespace) -> int:
    md = review_mod.render_test_plan(args.title,
                                     args.feature or [],
                                     args.interface or [])
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"测试方案已写入 {args.out}")
    else:
        print(md)
    return 0


def _force_utf8() -> None:
    """Windows 控制台默认 GBK，中文/符号输出会抛 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    _force_utf8()
    p = argparse.ArgumentParser(prog="hwdk",
                                description="嵌入式硬件设计与验证工具集")
    sub = p.add_subparsers(dest="cmd")

    c = sub.add_parser("calc", help="设计计算（电源/信号链/接口）")
    c.add_argument("kind", choices=["ldo", "dcdc", "adc", "aa", "i2c", "uart",
                                    "can", "can-term", "spi", "usb"])
    c.add_argument("--vin", type=float, default=5.0)
    c.add_argument("--vout", type=float, default=3.3)
    c.add_argument("--iout", type=float, default=0.5)
    c.add_argument("--eff", type=float, default=0.90, help="DC-DC 效率")
    c.add_argument("--theta", type=float, default=60.0, help="θJA °C/W")
    c.add_argument("--tamb", type=float, default=25.0, help="环境温度 °C")
    c.add_argument("--vref", type=float, default=3.3)
    c.add_argument("--bits", type=int, default=12)
    c.add_argument("--full-scale", dest="full_scale", type=float, default=10.0)
    c.add_argument("--span", type=float, default=10.0)
    c.add_argument("--r", type=float, default=1000.0, help="抗混叠电阻 Ω")
    c.add_argument("--c", type=float, default=100e-9, help="抗混叠电容 F")
    c.add_argument("--fsignal", type=float, default=100.0, help="信号带宽 Hz")
    c.add_argument("--fsample", type=float, default=20000.0, help="采样率 Hz")
    c.add_argument("--vdd", type=float, default=3.3)
    c.add_argument("--cbus", type=float, default=200.0, help="I2C 总线电容 pF")
    c.add_argument("--tr", type=float, default=300.0, help="上升时间 ns")
    c.add_argument("--fsys", type=float, default=168000000.0, help="UART 时钟 Hz")
    c.add_argument("--baud", type=int, default=115200)
    c.add_argument("--oversampling", type=int, default=16)
    c.add_argument("--fclock", type=float, default=42000000.0, help="CAN 时钟 Hz")
    c.add_argument("--bitrate", type=int, default=500000)
    c.add_argument("--sample-point", dest="sample_point", type=float, default=0.875)
    c.add_argument("--nodes", type=int, default=4)
    c.add_argument("--stub", type=float, default=0.3, help="CAN 支线长度 m")
    c.add_argument("--tsu", type=float, default=5.0, help="SPI 建立时间 ns")
    c.add_argument("--thold", type=float, default=3.0, help="SPI 保持时间 ns")
    c.add_argument("--tprop", type=float, default=6.0, help="SPI 传播延迟 ns")
    c.add_argument("--speed", default="full", help="USB 速率 low/full/high")
    c.add_argument("--json", default=None, help="把结果写成 JSON")
    c.set_defaults(func=cmd_calc)

    b = sub.add_parser("bom", help="校验 BOM 清单")
    b.add_argument("file", help="BOM JSON 文件")
    b.add_argument("-o", "--out", default=None, help="输出 Markdown 报告")
    b.add_argument("--csv", default=None, help="导出标准 BOM CSV")
    b.set_defaults(func=cmd_bom)

    ck = sub.add_parser("checklist", help="输出硬件设计评审清单")
    ck.add_argument("-o", "--out", default=None)
    ck.set_defaults(func=cmd_checklist)

    rv = sub.add_parser("review", help="按回答评估设计评审结果")
    rv.add_argument("file", help="评审 JSON（answers / notes）")
    rv.add_argument("-o", "--out", default=None)
    rv.set_defaults(func=cmd_review)

    tp = sub.add_parser("testplan", help="生成硬件测试方案")
    tp.add_argument("--title", default="硬件模块")
    tp.add_argument("--feature", action="append", help="测试范围（可多次）")
    tp.add_argument("--interface", action="append", help="接口（I2C/SPI/UART/CAN/USB）")
    tp.add_argument("-o", "--out", default=None)
    tp.set_defaults(func=cmd_testplan)

    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
