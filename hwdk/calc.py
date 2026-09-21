"""hwdk.calc — 硬件设计计算：电源树 / 信号链 / 接口电路

把嵌入式硬件设计里**可计算、可复核**的部分做成函数，避免"凭经验拍数"：

  电源树   LDO 与 DC-DC 的效率、功耗、结温估算；去耦电容配置参考
  信号链   运放增益/带宽/噪声、ADC LSB 与有效位数、抗混叠滤波器截止频率、共模抑制
  接口电路 I2C 上拉电阻取值范围、UART 波特率误差、CAN 位定时与终端电阻、
           SPI 最大时钟、USB 串联匹配电阻

每个函数都返回带推导过程的 `CalcResult`，可直接贴进设计文档做"计算书"。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ------------------------------------------------------------------ 结果容器


@dataclass
class CalcResult:
    """一次计算的完整结果：结论 + 推导步骤 + 判定。"""
    name: str
    ok: bool
    summary: str
    steps: List[str] = field(default_factory=list)
    values: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def add(self, step: str) -> "CalcResult":
        self.steps.append(step)
        return self

    def warn(self, msg: str) -> "CalcResult":
        self.warnings.append(msg)
        return self

    def to_dict(self) -> dict:
        return {
            "name": self.name, "ok": self.ok, "summary": self.summary,
            "steps": self.steps,
            "values": {k: round(v, 6) for k, v in self.values.items()},
            "warnings": self.warnings,
        }


# ==================================================================== 电源树
def ldo_power(v_in: float, v_out: float, i_out: float,
              theta_ja: float = 60.0, t_ambient: float = 25.0,
              t_j_max: float = 125.0) -> CalcResult:
    """LDO 功耗与结温估算。

    LDO 把压差全部变成热：P_diss = (Vin - Vout) * Iout。
    结温 T_j = T_amb + P_diss * θ_JA，要求 T_j < T_j_max（通常留 20% 余量）。
    """
    r = CalcResult("LDO 功耗与结温", True, "")
    if v_in <= v_out:
        r.ok = False
        r.summary = f"输入 {v_in} V 不高于输出 {v_out} V，LDO 无法工作"
        return r

    drop = v_in - v_out
    p_diss = drop * i_out
    efficiency = v_out / v_in
    t_j = t_ambient + p_diss * theta_ja

    r.add(f"压差 ΔV = {v_in} - {v_out} = {drop:.3f} V")
    r.add(f"耗散功率 P = ΔV × Iout = {drop:.3f} × {i_out} = {p_diss:.4f} W")
    r.add(f"效率 η = Vout/Vin = {efficiency:.1%}")
    r.add(f"结温 Tj = {t_ambient} + {p_diss:.4f} × {theta_ja} = {t_j:.1f} °C")
    r.values = {"drop_v": drop, "p_diss_w": p_diss, "efficiency": efficiency, "t_j_c": t_j}

    if t_j > t_j_max:
        r.ok = False
        r.summary = f"结温 {t_j:.1f} °C 超过上限 {t_j_max} °C，需降流或换 DC-DC"
    else:
        r.summary = (f"P_diss = {p_diss:.3f} W，η = {efficiency:.1%}，"
                     f"Tj = {t_j:.1f} °C（余量 {t_j_max - t_j:.1f} °C）")
    if t_j > t_j_max * 0.8:
        r.warn(f"结温已用掉 80% 余量，建议核散热铜箔面积或降低 Vout 压差")
    return r


def dcdc_power(v_in: float, v_out: float, i_out: float, efficiency: float = 0.90,
               f_sw_khz: float = 500.0) -> CalcResult:
    """DC-DC 输入功率、损耗与效率核查。"""
    r = CalcResult("DC-DC 功率预算", True, "")
    if not 0.0 < efficiency < 1.0:
        r.ok = False
        r.summary = f"效率 {efficiency} 非法（应在 0~1 之间）"
        return r
    p_out = v_out * i_out
    p_in = p_out / efficiency
    p_loss = p_in - p_out
    i_in = p_in / v_in if v_in else 0.0

    r.add(f"输出功率 Pout = {v_out} × {i_out} = {p_out:.3f} W")
    r.add(f"输入功率 Pin = Pout/η = {p_out:.3f}/{efficiency} = {p_in:.3f} W")
    r.add(f"损耗 Ploss = {p_loss:.3f} W，输入电流 Iin = Pin/Vin = {i_in:.3f} A")
    r.values = {"p_out_w": p_out, "p_in_w": p_in, "p_loss_w": p_loss, "i_in_a": i_in}
    r.summary = (f"Pin = {p_in:.3f} W（Iin = {i_in:.3f} A），"
                 f"Ploss = {p_loss:.3f} W @ η={efficiency:.0%}")
    if p_loss > 0.5:
        r.warn(f"单路损耗 {p_loss:.3f} W 偏大，注意电感饱和电流与散热")
    r.add(f"开关频率参考 {f_sw_khz:.0f} kHz（电感与输出电容按此选型）")
    return r


def power_tree(rails: List[dict], t_ambient: float = 25.0) -> CalcResult:
    """整机电源树总功耗与总效率。

    rails 每项：{name, kind('ldo'|'dcdc'), vin, vout, iout, efficiency?}
    """
    r = CalcResult("电源树总功耗", True, "")
    total_in = 0.0
    detail: List[str] = []
    for rail in rails:
        kind = str(rail.get("kind", "ldo")).lower()
        vin, vout, iout = rail["vin"], rail["vout"], rail["iout"]
        if kind == "dcdc":
            eff = rail.get("efficiency", 0.90)
            p_in = (vout * iout) / eff
        else:
            p_in = vin * (iout * vout / vin) if vin else 0.0
            p_in = vout * iout + (vin - vout) * iout   # LDO：输入功率 = Vin*Iout
            p_in = vin * iout
        total_in += p_in
        detail.append(f"{rail['name']:<10} {kind.upper():<5} {vin:>6.2f}V→{vout:<6.2f}V "
                      f"{iout:>6.3f}A  Pin={p_in:.3f} W")
    r.steps.extend(detail)
    r.values = {"total_input_w": total_in, "rail_count": float(len(rails))}
    r.summary = f"{len(rails)} 路电源，总输入功率 {total_in:.3f} W（@ {t_ambient} °C）"
    if total_in > 10.0:
        r.warn(f"总功耗 {total_in:.1f} W 偏高，确认散热与输入线径")
    return r


def decoupling_caps(ic_count: int, high_speed_pins: int = 0,
                    bulk_uf: float = 10.0) -> CalcResult:
    """去耦电容数量参考：每个电源脚一个 100 nF，每 3~5 个 IC 一个 10 µF 体电容。"""
    n_100n = ic_count + high_speed_pins
    n_bulk = max(1, (ic_count + 3) // 4)
    r = CalcResult("去耦电容配置", True, "")
    r.add(f"100 nF 就近去耦：每个电源脚 1 只 -> {ic_count} 只（+ 高速脚 {high_speed_pins} 只）= {n_100n} 只")
    r.add(f"{bulk_uf:.0f} µF 体电容：每 3~5 个 IC 1 只 -> {n_bulk} 只")
    r.values = {"cap_100n": float(n_100n), "cap_bulk": float(n_bulk)}
    r.summary = f"建议 100 nF × {n_100n} + {bulk_uf:.0f} µF × {n_bulk}"
    if high_speed_pins > 0:
        r.warn("有高速信号脚：去耦电容必须贴近引脚，回流路径尽量短")
    return r


# ================================================================== 信号链
def opamp_gain(r_g: float, r_f: float, gain_bw_hz: float,
               gbp_hz: float) -> CalcResult:
    """同相放大器增益与可用带宽核查（INA333 这类仪放按额定增益处理）。

    增益 G = 1 + Rf/Rg；实际带宽 = GBW / G。
    """
    r = CalcResult("运放增益与带宽", True, "")
    if r_g <= 0:
        r.ok = False
        r.summary = "Rg 必须大于 0"
        return r
    g = 1.0 + r_f / r_g
    bw = gbp_hz / g
    r.add(f"增益 G = 1 + Rf/Rg = 1 + {r_f}/{r_g} = {g:.2f}（{20 * _log10(g):.1f} dB）")
    r.add(f"闭环带宽 BW = GBW/G = {gbp_hz:.0f}/{g:.2f} = {bw:.1f} Hz")
    r.values = {"gain": g, "gain_db": 20 * _log10(g), "bandwidth_hz": bw}
    r.summary = f"G = {g:.2f}，可用带宽 {bw:.1f} Hz"
    if bw < gain_bw_hz:
        r.ok = False
        r.summary = f"带宽 {bw:.1f} Hz 低于所需 {gain_bw_hz:.1f} Hz"
    return r


def adc_resolution(v_ref: float, bits: int, full_scale: float,
                   span: float) -> CalcResult:
    """ADC 分辨率：LSB 电压、LSB 对应被测量、有效位数需求。"""
    r = CalcResult("ADC 分辨率", True, "")
    if bits <= 0 or v_ref <= 0:
        r.ok = False
        r.summary = "Vref 与位数必须为正"
        return r
    lsb_v = v_ref / (2 ** bits)
    lsb_meas = lsb_v * (span / full_scale) if full_scale else 0.0
    r.add(f"LSB 电压 = Vref/2^bits = {v_ref}/{2 ** bits} = {lsb_v * 1000:.4f} mV")
    r.add(f"满量程 {full_scale} 对应被测量跨度 {span} -> 每 LSB = {lsb_meas:.6g}")
    r.values = {"lsb_v": lsb_v, "lsb_measured": lsb_meas, "codes": float(2 ** bits)}
    r.summary = f"{bits} bit @ {v_ref} V：LSB = {lsb_v * 1000:.4f} mV"
    if lsb_meas and lsb_meas > span * 0.01:
        r.warn(f"单 LSB 已占满量程跨度的 {lsb_meas / span:.1%}，分辨率可能不够")
    return r


def antialias_filter(r_ohm: float, c_f: float, f_signal_hz: float,
                     f_sample_hz: float) -> CalcResult:
    """RC 抗混叠滤波器：截止频率与在采样率处的衰减。"""
    r = CalcResult("抗混叠滤波器", True, "")
    if r_ohm <= 0 or c_f <= 0:
        r.ok = False
        r.summary = "R 与 C 必须为正"
        return r
    fc = 1.0 / (2 * 3.141592653589793 * r_ohm * c_f)
    # 一阶 RC 在采样频率处的衰减
    att = 1.0 / (1.0 + (f_sample_hz / fc) ** 2) ** 0.5
    att_db = 20 * _log10(att)
    r.add(f"截止频率 fc = 1/(2πRC) = 1/(2π×{r_ohm}×{c_f:g}) = {fc:.1f} Hz")
    r.add(f"在采样率 {f_sample_hz:.0f} Hz 处增益 = {att:.6f}（{att_db:.1f} dB）")
    r.values = {"fc_hz": fc, "attenuation_at_fs": att, "attenuation_db": att_db}
    r.summary = f"fc = {fc:.1f} Hz，{f_sample_hz:.0f} Hz 处衰减 {att_db:.1f} dB"
    if fc < f_signal_hz:
        r.ok = False
        r.summary = f"fc {fc:.1f} Hz 低于信号带宽 {f_signal_hz:.1f} Hz，会削弱有用信号"
    nyq = f_sample_hz / 2.0
    if fc > nyq:
        r.warn(f"fc {fc:.1f} Hz 高于奈奎斯特频率 {nyq:.1f} Hz，抗混叠作用有限")
    return r


# ================================================================ 接口电路
def i2c_pullup(v_dd: float, c_bus_pf: float, rise_time_ns: float = 300.0,
               vol_max: float = 0.4, i_ol_ma: float = 3.0) -> CalcResult:
    """I2C 上拉电阻取值范围。

    上限由上升时间决定：Rp_max = tr / (0.8473 × Cbus)
    下限由灌电流能力决定：Rp_min = (Vdd - Vol_max) / Iol
    """
    r = CalcResult("I2C 上拉电阻", True, "")
    c_f = c_bus_pf * 1e-12
    tr_s = rise_time_ns * 1e-9
    rp_max = tr_s / (0.8473 * c_f) if c_f else 0.0
    rp_min = (v_dd - vol_max) / (i_ol_ma / 1000.0) if i_ol_ma else 0.0

    r.add(f"总线电容 Cbus = {c_bus_pf:.0f} pF，上升时间要求 tr ≤ {rise_time_ns:.0f} ns")
    r.add(f"上限 Rp_max = tr/(0.8473×Cbus) = {rp_max:.1f} Ω")
    r.add(f"下限 Rp_min = (Vdd-Vol)/Iol = ({v_dd}-{vol_max})/{i_ol_ma} mA = {rp_min:.1f} Ω")
    r.values = {"rp_min_ohm": rp_min, "rp_max_ohm": rp_max}
    # 常用档位：从 E24 里挑一个落在区间中部的
    std = [1000, 1200, 1500, 1800, 2200, 2700, 3300, 3900, 4700, 5600, 6800, 10000]
    pick = [x for x in std if rp_min <= x <= rp_max]
    if pick:
        best = min(pick, key=lambda x: abs(x - (rp_min + rp_max) / 2))
        r.add(f"推荐标称值（E24）：{best} Ω（区间内可选：{pick}）")
        r.summary = f"Rp ∈ [{rp_min:.0f}, {rp_max:.0f}] Ω，推荐 {best} Ω"
    else:
        r.ok = False
        r.summary = f"无合适标称值：区间 [{rp_min:.0f}, {rp_max:.0f}] Ω 为空，需降总线电容或提速"
    return r


def uart_baud_error(f_sys: float, baud: int, oversampling: int = 16) -> CalcResult:
    """UART 波特率误差：分频系数取整带来的偏差，一般要求 < 2~3%。"""
    r = CalcResult("UART 波特率误差", True, "")
    if baud <= 0 or f_sys <= 0:
        r.ok = False
        r.summary = "波特率与时钟频率必须为正"
        return r
    div_exact = f_sys / (baud * oversampling)
    div_int = max(1, round(div_exact))
    actual = f_sys / (div_int * oversampling)
    err = (actual - baud) / baud
    r.add(f"理想分频 = f_sys/(baud×{oversampling}) = {f_sys:.0f}/({baud}×{oversampling}) = {div_exact:.4f}")
    r.add(f"取整分频 = {div_int} -> 实际波特率 = {actual:.2f} bps")
    r.add(f"误差 = (实际-标称)/标称 = {err * 100:+.3f}%")
    r.values = {"divisor": float(div_int), "actual_baud": actual, "error": err}
    r.summary = f"USARTDIV = {div_int}，实际 {actual:.2f} bps，误差 {err * 100:+.3f}%"
    if abs(err) > 0.03:
        r.ok = False
        r.summary += "（超过 3%，长帧易错，建议换时钟或波特率）"
    elif abs(err) > 0.02:
        r.warn("误差在 2%~3% 之间，建议核收端采样点与校验方式")
    return r


def can_bit_timing(f_clock: float, bitrate: int, sample_point: float = 0.875
                   ) -> CalcResult:
    """CAN 位定时参数：tq 数、BS1/BS2、采样点与误差。

    经典 CAN：一个位 = SYNC(1) + BS1 + BS2（单位 tq），
    采样点 = (1 + BS1) / (1 + BS1 + BS2)，推荐 87.5%（CiA 建议）。
    """
    r = CalcResult("CAN 位定时", True, "")
    if f_clock <= 0 or bitrate <= 0:
        r.ok = False
        r.summary = "时钟与波特率必须为正"
        return r
    tq_total_exact = f_clock / bitrate
    tq_total = max(4, round(tq_total_exact))
    bs_total = tq_total - 1                      # 去掉 SYNC
    bs1 = max(1, round(bs_total * sample_point))
    bs2 = max(1, bs_total - bs1)
    actual_sp = (1 + bs1) / (1 + bs1 + bs2)
    actual_bitrate = f_clock / (1 + bs1 + bs2)
    err = (actual_bitrate - bitrate) / bitrate

    r.add(f"每比特 tq 数 = f_clock/bitrate = {f_clock:.0f}/{bitrate} = {tq_total_exact:.3f} -> 取 {tq_total}")
    r.add(f"BS1 = {bs1} tq，BS2 = {bs2} tq（SYNC 固定 1 tq）")
    r.add(f"采样点 = (1+BS1)/(1+BS1+BS2) = {actual_sp:.1%}（目标 {sample_point:.1%}）")
    r.add(f"实际波特率 = {actual_bitrate:.1f} bps，误差 {err * 100:+.3f}%")
    r.values = {"bs1": float(bs1), "bs2": float(bs2), "sample_point": actual_sp,
                "actual_bitrate": actual_bitrate, "error": err}
    r.summary = f"BS1={bs1} BS2={bs2}，采样点 {actual_sp:.1%}，误差 {err * 100:+.3f}%"
    if abs(actual_sp - sample_point) > 0.02:
        r.warn(f"采样点偏离目标 {abs(actual_sp - sample_point) * 100:.1f}%，建议调整时钟或换 tq 分配")
    if abs(err) > 0.005:
        r.warn("波特率误差 > 0.5%，长总线或高温下需复核")
    return r


def can_termination(node_count: int, stub_len_m: float,
                    bitrate_kbps: float) -> CalcResult:
    """CAN 终端电阻与支线长度核查。"""
    r = CalcResult("CAN 终端与支线", True, "")
    r.add(f"总线两端各 120 Ω，并联等效 {120 * 120 / (120 + 120):.0f} Ω（仅两端装，中间节点不装）")
    r.steps.append(f"节点数 {node_count}，支线（stub）总长 {stub_len_m} m")
    r.values = {"termination_ohm": 60.0, "node_count": float(node_count)}
    # 经验上限：支线长度与速率相关（1 Mbps 约 0.3 m，125 kbps 约 6 m）
    limit = {1000: 0.3, 500: 0.6, 250: 1.2, 125: 6.0, 50: 15.0}
    key = min(limit, key=lambda k: abs(k - bitrate_kbps))
    allowed = limit[key]
    r.add(f"{bitrate_kbps:g} kbps 下支线建议 ≤ {allowed} m（按 {key} kbps 档）")
    if stub_len_m > allowed:
        r.ok = False
        r.summary = f"支线 {stub_len_m} m 超过 {bitrate_kbps:g} kbps 建议上限 {allowed} m"
    else:
        r.summary = f"支线 {stub_len_m} m ≤ {allowed} m，终端 120 Ω×2 合格"
    if node_count > 30:
        r.warn("节点数 > 30，注意总线负载与收发器驱动能力")
    return r


def spi_max_clock(t_setup_ns: float, t_hold_ns: float, t_prop_ns: float) -> CalcResult:
    """SPI 最大时钟：由建立/保持/传播延迟反推半周期下限。"""
    r = CalcResult("SPI 最大时钟", True, "")
    half = max(t_setup_ns, t_hold_ns, t_prop_ns * 2) * 1e-9
    f_max = 1.0 / (2 * half) if half else 0.0
    r.add(f"约束：半周期 ≥ max(t_su={t_setup_ns} ns, t_h={t_hold_ns} ns, 2×t_prop={t_prop_ns * 2} ns)")
    r.add(f"半周期下限 = {half * 1e9:.1f} ns -> f_max = 1/(2×半周期) = {f_max / 1e6:.2f} MHz")
    r.values = {"half_period_ns": half * 1e9, "f_max_hz": f_max}
    r.summary = f"建议 SCLK ≤ {f_max / 1e6:.2f} MHz（按 10% 余量取 {f_max / 1.1 / 1e6:.2f} MHz）"
    r.warn("实际还要扣除走线延时与从机建立时间，建议按 70% 取值")
    return r


def usb_series_resistor(speed: str = "full") -> CalcResult:
    """USB 串联匹配电阻与差分阻抗要求（回路匹配，非端接）。"""
    r = CalcResult("USB 匹配与阻抗", True, "")
    table = {
        "low":  (1.5,  "1.5 Mbps",  90.0, 0.0),
        "full": (12.0, "12 Mbps",   90.0, 22.0),
        "high": (480.0, "480 Mbps", 90.0, 0.0),
    }
    key = speed.lower()
    if key not in table:
        r.ok = False
        r.summary = f"未知速率档 {speed}（可选 low/full/high）"
        return r
    mbps, name, z_diff, series = table[key]
    r.add(f"速率档：{name}（{key} speed）")
    r.add(f"差分阻抗目标 {z_diff:.0f} Ω（USB 2.0 全速/高速一致要求）")
    if series:
        r.add(f"全速/低速建议在 D+/D- 串 {series:.0f} Ω 匹配电阻（靠近 MCU 端），"
              f"高速需去掉此电阻并做阻抗控制")
    else:
        r.add("高速不串匹配电阻，靠 PCB 差分阻抗与端接控制；需 90 Ω 差分走线")
    r.values = {"diff_impedance_ohm": z_diff, "series_ohm": series}
    r.summary = (f"{name}：差分 {z_diff:.0f} Ω"
                 + (f"，串 {series:.0f} Ω 匹配电阻" if series else "，不串匹配电阻"))
    if key == "high":
        r.warn("高速 USB：需等长走线、90 Ω 差分阻抗、避免过孔与直角")
    return r


def _log10(x: float) -> float:
    import math
    return math.log10(x) if x > 0 else float("-inf")
