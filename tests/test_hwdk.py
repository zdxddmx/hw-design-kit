"""test_hwdk.py — 单元测试（标准库 unittest，零第三方依赖）

  T1 calc-power   LDO 功耗/结温、DC-DC 功率、电源树、去耦
  T2 calc-signal  运放增益带宽、ADC 分辨率、抗混叠
  T3 calc-iface   I2C 上拉、UART 波特率误差、CAN 位定时与终端、SPI 时钟、USB 匹配
  T4 bom          BOM 校验（位号重复/格式/封装缺失/参数缺失/单点料/可合并）与导出
  T5 review       评审清单、评审评估、测试方案与测试报告渲染
  T6 cli          命令行各子命令

运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwdk import bom as bom_mod                    # noqa: E402
from hwdk import calc as calc_mod                  # noqa: E402
from hwdk import review as review_mod              # noqa: E402
from hwdk.cli import main                          # noqa: E402


def _near(a, b, tol=1e-6):
    return abs(a - b) <= tol


# ------------------------------------------------------------- T1 电源
class TestPower(unittest.TestCase):
    def test_ldo_power_and_temp(self):
        r = calc_mod.ldo_power(5.0, 3.3, 0.2, theta_ja=60.0, t_ambient=25.0)
        self.assertTrue(r.ok, r.summary)
        self.assertTrue(_near(r.values["p_diss_w"], 0.34, 1e-9))
        self.assertTrue(_near(r.values["efficiency"], 3.3 / 5.0, 1e-9))
        self.assertTrue(_near(r.values["t_j_c"], 25.0 + 0.34 * 60.0, 1e-9))

    def test_ldo_over_temperature(self):
        # 24V -> 5V @1A：19 W 全变热，必然超结温
        r = calc_mod.ldo_power(24.0, 5.0, 1.0)
        self.assertFalse(r.ok)
        self.assertIn("超过上限", r.summary)
        self.assertTrue(any("80%" in w for w in r.warnings))

    def test_ldo_invalid_vin(self):
        r = calc_mod.ldo_power(3.0, 3.3, 0.1)
        self.assertFalse(r.ok)
        self.assertIn("无法工作", r.summary)

    def test_dcdc_power(self):
        r = calc_mod.dcdc_power(24.0, 5.0, 1.0, efficiency=0.90)
        self.assertTrue(r.ok)
        self.assertTrue(_near(r.values["p_out_w"], 5.0, 1e-9))
        self.assertTrue(_near(r.values["p_in_w"], 5.0 / 0.90, 1e-9))
        self.assertTrue(_near(r.values["i_in_a"], (5.0 / 0.90) / 24.0, 1e-9))

    def test_dcdc_invalid_efficiency(self):
        r = calc_mod.dcdc_power(12.0, 5.0, 1.0, efficiency=1.2)
        self.assertFalse(r.ok)

    def test_power_tree_totals(self):
        rails = [
            {"name": "5V", "kind": "dcdc", "vin": 24.0, "vout": 5.0, "iout": 1.0,
             "efficiency": 0.9},
            {"name": "3V3", "kind": "ldo", "vin": 5.0, "vout": 3.3, "iout": 0.5},
        ]
        r = calc_mod.power_tree(rails)
        expect = (5.0 * 1.0 / 0.9) + (5.0 * 0.5)
        self.assertTrue(_near(r.values["total_input_w"], expect, 1e-9),
                        f"got {r.values['total_input_w']} want {expect}")
        self.assertEqual(r.values["rail_count"], 2.0)
        self.assertEqual(len(r.steps), 2)

    def test_decoupling(self):
        r = calc_mod.decoupling_caps(ic_count=6, high_speed_pins=2)
        self.assertEqual(r.values["cap_100n"], 8.0)
        self.assertEqual(r.values["cap_bulk"], 2.0)
        self.assertTrue(r.warnings)


# ----------------------------------------------------------- T2 信号链
class TestSignal(unittest.TestCase):
    def test_opamp_gain_bandwidth(self):
        r = calc_mod.opamp_gain(r_g=249.0, r_f=49751.0, gain_bw_hz=1000.0,
                                gbp_hz=500000.0)
        self.assertTrue(_near(r.values["gain"], 1 + 49751.0 / 249.0, 1e-6))
        self.assertTrue(_near(r.values["bandwidth_hz"],
                              500000.0 / r.values["gain"], 1e-6))

    def test_opamp_insufficient_bandwidth(self):
        r = calc_mod.opamp_gain(249.0, 49751.0, gain_bw_hz=50000.0,
                                gbp_hz=500000.0)
        self.assertFalse(r.ok)
        self.assertIn("低于所需", r.summary)

    def test_adc_resolution(self):
        r = calc_mod.adc_resolution(3.3, 12, full_scale=10.0, span=10.0)
        self.assertTrue(_near(r.values["lsb_v"], 3.3 / 4096, 1e-12))
        self.assertTrue(_near(r.values["lsb_measured"], (3.3 / 4096) * 1.0, 1e-12))
        self.assertEqual(r.values["codes"], 4096.0)

    def test_adc_resolution_warning(self):
        # 8 bit + 小量程 -> 单 LSB 占比过大
        r = calc_mod.adc_resolution(3.3, 8, full_scale=1.0, span=1.0)
        self.assertTrue(r.warnings)

    def test_antialias_ok(self):
        # R=1k, C=100n -> fc ≈ 1591 Hz，fs=20k 抗混叠有效
        r = calc_mod.antialias_filter(1000.0, 100e-9, f_signal_hz=100.0,
                                      f_sample_hz=20000.0)
        self.assertTrue(r.ok, r.summary)
        self.assertTrue(_near(r.values["fc_hz"], 1 / (2 * 3.141592653589793 * 1e-4),
                              1e-6))

    def test_antialias_fc_too_low(self):
        r = calc_mod.antialias_filter(1000.0, 100e-6, f_signal_hz=100.0,
                                      f_sample_hz=20000.0)
        self.assertFalse(r.ok)
        self.assertIn("削弱有用信号", r.summary)

    def test_antialias_fc_above_nyquist_warns(self):
        r = calc_mod.antialias_filter(100.0, 1e-9, f_signal_hz=1.0,
                                      f_sample_hz=20000.0)
        self.assertTrue(any("奈奎斯特" in w for w in r.warnings))


# ----------------------------------------------------------- T3 接口
class TestIface(unittest.TestCase):
    def test_i2c_pullup_range(self):
        r = calc_mod.i2c_pullup(3.3, c_bus_pf=200.0, rise_time_ns=300.0)
        self.assertTrue(r.ok, r.summary)
        self.assertTrue(r.values["rp_min_ohm"] < r.values["rp_max_ohm"])
        self.assertIn("推荐", r.summary)

    def test_i2c_pullup_impossible(self):
        # 总线电容极大 -> 上限低于下限，无解
        r = calc_mod.i2c_pullup(3.3, c_bus_pf=20000.0, rise_time_ns=100.0)
        self.assertFalse(r.ok)
        self.assertIn("为空", r.summary)

    def test_uart_baud_exact(self):
        # 168 MHz / (115200*16) = 91.1458 -> 取 91 -> 误差约 0.16%
        r = calc_mod.uart_baud_error(168000000.0, 115200, 16)
        self.assertTrue(r.ok, r.summary)
        self.assertLess(abs(r.values["error"]), 0.03)

    def test_uart_baud_bad(self):
        # 故意选一个分频很差的组合
        r = calc_mod.uart_baud_error(1000000.0, 115200, 16)
        self.assertFalse(r.ok)
        self.assertIn("3%", r.summary)

    def test_can_bit_timing(self):
        r = calc_mod.can_bit_timing(42000000.0, 500000, 0.875)
        self.assertTrue(r.ok, r.summary)
        self.assertEqual(r.values["bs1"] + r.values["bs2"], 83.0)
        self.assertTrue(abs(r.values["sample_point"] - 0.875) < 0.02)
        self.assertTrue(_near(r.values["actual_bitrate"], 500000.0, 1e-6))

    def test_can_termination_ok_and_bad(self):
        ok = calc_mod.can_termination(node_count=4, stub_len_m=0.3,
                                      bitrate_kbps=500.0)
        self.assertTrue(ok.ok, ok.summary)
        bad = calc_mod.can_termination(node_count=4, stub_len_m=10.0,
                                       bitrate_kbps=500.0)
        self.assertFalse(bad.ok)
        self.assertIn("超过", bad.summary)

    def test_spi_max_clock(self):
        r = calc_mod.spi_max_clock(t_setup_ns=5.0, t_hold_ns=3.0, t_prop_ns=6.0)
        self.assertTrue(_near(r.values["f_max_hz"], 1.0 / (2 * 12e-9), 1.0))
        self.assertTrue(r.warnings)

    def test_usb_series_resistor(self):
        full = calc_mod.usb_series_resistor("full")
        self.assertTrue(full.ok)
        self.assertEqual(full.values["series_ohm"], 22.0)
        high = calc_mod.usb_series_resistor("high")
        self.assertEqual(high.values["series_ohm"], 0.0)
        self.assertTrue(high.warnings)
        bad = calc_mod.usb_series_resistor("super")
        self.assertFalse(bad.ok)

    def test_calc_result_to_dict(self):
        d = calc_mod.ldo_power(5.0, 3.3, 0.2).to_dict()
        for k in ("name", "ok", "summary", "steps", "values", "warnings"):
            self.assertIn(k, d)
        self.assertIsInstance(d["values"]["p_diss_w"], float)


# --------------------------------------------------------------- T4 BOM
class TestBom(unittest.TestCase):
    def _good(self):
        return [
            {"ref": "R1,R2", "value": "10k", "package": "0603", "qty": 2,
             "category": "resistor", "note": "tolerance 1% power 0.1W"},
            {"ref": "C1", "value": "100nF", "package": "0603", "qty": 1,
             "category": "capacitor", "note": "tolerance 10% voltage 50V"},
            {"ref": "U1", "value": "STM32F103", "package": "LQFP48", "qty": 1,
             "category": "ic", "part_number": "STM32F103C8T6",
             "alternatives": ["GD32F103"]},
        ]

    def test_good_bom_passes(self):
        rep = bom_mod.validate_bom(self._good())
        self.assertTrue(rep.ok, [i.message for i in rep.errors])
        self.assertEqual(rep.total_components(), 4)
        self.assertEqual(rep.by_category()["resistor"], 2)

    def test_duplicate_ref_detected(self):
        items = self._good()
        items.append({"ref": "R1", "value": "1k", "package": "0603", "qty": 1,
                      "category": "resistor"})
        rep = bom_mod.validate_bom(items)
        self.assertFalse(rep.ok)
        self.assertTrue(any(i.rule == "ref-duplicated" for i in rep.errors))

    def test_bad_ref_format(self):
        # 数字在前（1R）与带分隔符（R-1）都不符合规范；
        # 注意 RES1 是合法的（字母+数字），不应被误报
        for bad in ("1R", "R-1", "R 1"):
            rep = bom_mod.validate_bom([
                {"ref": bad, "value": "10k", "package": "0603", "qty": 1,
                 "category": "resistor"}])
            self.assertTrue(any(i.rule == "ref-format" for i in rep.errors),
                            f"{bad} 应被判为位号格式错误")
        ok = bom_mod.validate_bom([
            {"ref": "RES1", "value": "10k", "package": "0603", "qty": 1,
             "category": "resistor", "note": "tolerance 1% power 0.1W"}])
        self.assertFalse(any(i.rule == "ref-format" for i in ok.errors),
                         "RES1 是合法位号，不应误报")

    def test_missing_value_and_package(self):
        rep = bom_mod.validate_bom([{"ref": "R9", "qty": 1}])
        rules = {i.rule for i in rep.errors}
        self.assertIn("value-missing", rules)
        self.assertIn("package-missing", rules)

    def test_qty_invalid(self):
        rep = bom_mod.validate_bom([
            {"ref": "R9", "value": "1k", "package": "0603", "qty": 0}])
        self.assertTrue(any(i.rule == "qty-invalid" for i in rep.errors))

    def test_passive_extra_warning(self):
        rep = bom_mod.validate_bom([
            {"ref": "R9", "value": "1k", "package": "0603", "qty": 1,
             "category": "resistor", "note": "tolerance 1%"}])   # 缺 power
        self.assertTrue(any("power" in i.message for i in rep.warnings))

    def test_single_source_warning(self):
        rep = bom_mod.validate_bom([
            {"ref": "U9", "value": "X", "package": "QFN", "qty": 1,
             "category": "ic", "part_number": "ABC123"}])
        self.assertTrue(any(i.rule == "single-source" for i in rep.warnings))

    def test_mergeable_warning(self):
        rep = bom_mod.validate_bom([
            {"ref": "R1", "value": "10k", "package": "0603", "qty": 1,
             "category": "resistor"},
            {"ref": "R2", "value": "10k", "package": "0603", "qty": 1,
             "category": "resistor"}])
        self.assertTrue(any(i.rule == "mergeable" for i in rep.warnings))

    def test_dnp_excluded_from_total(self):
        rep = bom_mod.validate_bom([
            {"ref": "R1", "value": "1k", "package": "0603", "qty": 1},
            {"ref": "R2", "value": "1k", "package": "0603", "qty": 1, "dnp": True}])
        self.assertEqual(rep.total_components(), 1)
        self.assertEqual(rep.total_components(include_dnp=True), 2)

    def test_exports(self):
        rep = bom_mod.validate_bom(self._good())
        csv_text = bom_mod.to_csv(rep)
        self.assertIn("ref,category,value", csv_text)
        self.assertIn("STM32F103", csv_text)
        md = bom_mod.to_markdown(rep)
        self.assertIn("# BOM 校验报告", md)
        self.assertIn("## 一、器件构成", md)
        d = rep.to_dict()
        self.assertEqual(d["total_refs"], 3)
        self.assertIn("by_category", d)


# ------------------------------------------------------------ T5 review
class TestReview(unittest.TestCase):
    def test_checklist_has_all_categories(self):
        cats = {i.category for i in review_mod.CHECKLIST}
        for c in ("电源", "信号链", "接口", "EMC/EMI", "DFM", "DFT", "文档"):
            self.assertIn(c, cats)
        self.assertGreaterEqual(len(review_mod.CHECKLIST), 25)
        ids = [i.id for i in review_mod.CHECKLIST]
        self.assertEqual(len(ids), len(set(ids)), "检查项编号重复")

    def test_evaluate_all_pass_ready(self):
        answers = {i.id: "pass" for i in review_mod.CHECKLIST}
        res = review_mod.evaluate_review(answers)
        self.assertTrue(res["ready"])
        self.assertEqual(res["failed"], 0)
        self.assertEqual(res["unanswered"], 0)

    def test_evaluate_critical_fail_blocks(self):
        answers = {i.id: "pass" for i in review_mod.CHECKLIST}
        crit = [i for i in review_mod.CHECKLIST if i.severity == "critical"][0]
        answers[crit.id] = "fail"
        res = review_mod.evaluate_review(answers, {crit.id: "封装待核对"})
        self.assertFalse(res["ready"])
        self.assertEqual(len(res["critical_failed"]), 1)
        self.assertEqual(res["critical_failed"][0]["note"], "封装待核对")

    def test_evaluate_unanswered_not_ready(self):
        res = review_mod.evaluate_review({})
        self.assertFalse(res["ready"])
        self.assertEqual(res["unanswered"], len(review_mod.CHECKLIST))

    def test_na_counts_separately(self):
        answers = {i.id: "na" for i in review_mod.CHECKLIST}
        res = review_mod.evaluate_review(answers)
        self.assertEqual(res["na"], len(review_mod.CHECKLIST))
        self.assertTrue(res["ready"])

    def test_render_checklist_markdown(self):
        md = review_mod.render_checklist()
        self.assertIn("# 硬件设计评审清单", md)
        self.assertIn("| PWR-01 |", md)

    def test_render_review_markdown(self):
        answers = {i.id: "pass" for i in review_mod.CHECKLIST}
        res = review_mod.evaluate_review(answers)
        md = review_mod.render_review(res)
        self.assertIn("是否具备投板条件：是", md)

    def test_test_plan_covers_interfaces(self):
        md = review_mod.render_test_plan("主控板", ["电源", "串口"],
                                         ["I2C", "UART", "CAN", "USB"])
        self.assertIn("上电检查表", md)
        for it in ("I2C", "UART", "CAN", "USB"):
            self.assertIn(it, md)
        self.assertIn("限流上电", md)

    def test_test_report_counts_and_issues(self):
        items = [
            {"step": "电源轨电压", "expected": "5.0 V", "measured": "5.02 V",
             "instrument": "万用表", "conclusion": "pass"},
            {"step": "CAN 帧收发", "expected": "正常", "measured": "无 ACK",
             "instrument": "示波器", "conclusion": "fail",
             "issue": "先查终端电阻与位定时"},
        ]
        md = review_mod.render_test_report("主控板", "REV-A", "2026-09-19", items)
        self.assertIn("通过率：50.0%", md)
        self.assertIn("## 二、问题与处理", md)
        self.assertIn("先查终端电阻与位定时", md)


# ---------------------------------------------------------------- T6 cli
class TestCli(unittest.TestCase):
    def test_calc_ldo_ok(self):
        self.assertEqual(main(["calc", "ldo", "--vin", "5", "--vout", "3.3",
                               "--iout", "0.2"]), 0)

    def test_calc_ldo_fail_returns_1(self):
        self.assertEqual(main(["calc", "ldo", "--vin", "24", "--vout", "5",
                               "--iout", "1.0"]), 1)

    def test_calc_json_output(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.json"
            main(["calc", "i2c", "--vdd", "3.3", "--cbus", "200", "--json", str(p)])
            self.assertTrue(p.exists())
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertTrue(data["ok"])

    def test_checklist_out(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.md"
            self.assertEqual(main(["checklist", "-o", str(p)]), 0)
            self.assertIn("硬件设计评审清单", p.read_text(encoding="utf-8"))

    def test_bom_ok_and_fail(self):
        good = [{"ref": "R1", "value": "10k", "package": "0603", "qty": 1,
                 "category": "resistor", "note": "tolerance 1% power 0.1W"}]
        bad = [{"ref": "R1", "qty": 1}]
        with tempfile.TemporaryDirectory() as d:
            gp = Path(d) / "good.json"
            bp = Path(d) / "bad.json"
            gp.write_text(json.dumps({"items": good}), encoding="utf-8")
            bp.write_text(json.dumps({"items": bad}), encoding="utf-8")
            self.assertEqual(main(["bom", str(gp), "-o", str(Path(d) / "g.md")]), 0)
            self.assertEqual(main(["bom", str(bp)]), 1)

    def test_review_ready_returns_0(self):
        answers = {i.id: "pass" for i in review_mod.CHECKLIST}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "rev.json"
            p.write_text(json.dumps({"answers": answers}), encoding="utf-8")
            self.assertEqual(main(["review", str(p)]), 0)

    def test_testplan_out(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tp.md"
            rc = main(["testplan", "--title", "X", "--interface", "I2C",
                       "-o", str(p)])
            self.assertEqual(rc, 0)
            self.assertIn("I2C", p.read_text(encoding="utf-8"))

    def test_no_args_shows_help(self):
        self.assertEqual(main([]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
