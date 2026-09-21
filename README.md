# hwdk — 嵌入式硬件设计与验证工具集

> 把嵌入式硬件设计里**可计算、可校验、可沉淀**的部分工具化。
>
> 面向硬件工程师的日常：**设计计算 → 设计评审 → BOM 校验 → 测试方案 → 测试报告**，
> 让"凭经验拍数"变成**可复核的计算书**，让"口头评审"变成**可归档的检查表**。

[![ci](https://github.com/meminehobe24435-cmyk/hw-design-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/meminehobe24435-cmyk/hw-design-kit/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.8%2B-blue)
![deps](https://img.shields.io/badge/dependencies-none-green)
![tests](https://img.shields.io/badge/tests-50%20passed-brightgreen)

---

## 1. 为什么做这个

硬件设计里最容易出错、也最该被工具化的四件事：

| 痛点 | hwdk 的做法 |
|---|---|
| **参数靠经验拍** —— LDO 结温、I2C 上拉、CAN 采样点、抗混叠截止频率，算错的代价是打样报废 | 13 个计算函数，每个都输出**完整推导步骤**，可直接贴进设计计算书 |
| **BOM 人手维护** —— 位号重复、封装漏填、阻容缺精度耐压、单点供货 | BOM 校验器覆盖 7 类规则，输出 Markdown 报告 + 标准 CSV |
| **设计评审靠口头** —— 问题散在聊天记录里，改版时想不起来上次踩过什么坑 | 33 项**结构化评审清单**（电源/信号链/接口/EMC-EMI/DFM-DFT/文档），critical 未通过直接阻塞投板 |
| **测试记录不统一** —— 每次上电检查步骤不一样，结论无法追溯 | 标准**测试方案模板 + 测试报告生成器**，要求记录原始数据与测量条件 |

---

## 2. 快速开始

```bash
# 设计计算（每个都会打印推导步骤）
python -m hwdk calc ldo   --vin 24 --vout 5 --iout 1.0      # LDO 功耗与结温
python -m hwdk calc dcdc  --vin 24 --vout 5 --iout 2 --eff 0.9
python -m hwdk calc adc   --vref 3.3 --bits 12 --full-scale 10 --span 10
python -m hwdk calc aa    --r 1000 --c 100e-9 --fsignal 100 --fsample 20000
python -m hwdk calc i2c   --vdd 3.3 --cbus 200 --tr 300
python -m hwdk calc uart  --fsys 168000000 --baud 115200
python -m hwdk calc can   --fclock 42000000 --bitrate 500000
python -m hwdk calc can-term --nodes 4 --stub 0.3 --bitrate 500000
python -m hwdk calc spi   --tsu 5 --thold 3 --tprop 6
python -m hwdk calc usb   --speed full

# 设计评审
python -m hwdk checklist -o checklist.md                    # 输出评审清单模板
python -m hwdk review examples/review_sample.json -o out.md # 评估评审结果

# BOM
python -m hwdk bom examples/bom_sample.json -o bom_report.md --csv bom.csv

# 测试
python -m hwdk testplan --title "数据采集主控板" --interface I2C --interface CAN -o tp.md
python -m unittest discover -s tests -v
```

`calc` 子命令在有警告/不通过时**返回非零退出码**，可以直接接进 CI 当设计检查门禁。

---

## 3. 目录结构

```
hwdk/
├── calc.py      设计计算：电源树 / 信号链 / 接口电路（13 个函数）
├── bom.py       BOM 校验（7 类规则）+ Markdown 报告 + 标准 CSV 导出
├── review.py    33 项设计评审清单 + 测试方案模板 + 测试报告生成
├── cli.py       命令行入口
└── __main__.py  python -m hwdk
examples/
├── bom_sample.json      示例 BOM（STM32F407 数据采集主控板）
├── review_sample.json   示例评审回答
└── *.md                 运行后生成的报告（评测时可删）
tests/
└── test_hwdk.py         50 项单元测试（unittest，零依赖）
```

---

## 4. 计算覆盖范围

### 电源
| 函数 | 算什么 |
|---|---|
| `ldo_power` | 耗散功率 `P=(Vin−Vout)×Iout`、效率、**结温** `Tj=Tamb+P×θJA`，超限报警 |
| `dcdc_power` | 输入功率、损耗、输入电流（按效率反推） |
| `power_tree` | 多路电源总输入功率与各路明细 |
| `decoupling_caps` | 100 nF / 体电容数量参考 |

### 信号链
| 函数 | 算什么 |
|---|---|
| `opamp_gain` | 增益 `G=1+Rf/Rg`、可用带宽 `BW=GBW/G`，带宽不足判不通过 |
| `adc_resolution` | LSB 电压、LSB 对应被测量、单 LSB 占比告警 |
| `antialias_filter` | RC 截止频率、采样率处衰减，**fc 超奈奎斯特告警** |

### 接口电路
| 函数 | 算什么 |
|---|---|
| `i2c_pullup` | `Rp_max=tr/(0.8473×Cbus)`、`Rp_min=(Vdd−Vol)/Iol`，并从 E24 推荐标称值 |
| `uart_baud_error` | 分频取整后的实际波特率与误差，>3% 判不通过 |
| `can_bit_timing` | tq 分配、BS1/BS2、**采样点**、实际波特率误差 |
| `can_termination` | 120 Ω×2 与**支线长度上限**（按速率档） |
| `spi_max_clock` | 由建立/保持/传播延迟反推最大时钟 |
| `usb_series_resistor` | 差分阻抗要求与全速 22 Ω 匹配电阻 |

---

## 5. 实测结果

### 单元测试

```
Ran 50 tests in 0.024s
OK
```

### 计算示例（真实输出）

**LDO 24V→5V @1A**（一个常见的设计错误）：

```
· 压差 ΔV = 24.0 - 5.0 = 19.000 V
· 耗散功率 P = ΔV × Iout = 19.000 × 1.0 = 19.0000 W
· 效率 η = Vout/Vin = 20.8%
· 结温 Tj = 25.0 + 19.0000 × 60.0 = 1165.0 °C
⚠ 结温已用掉 80% 余量，建议核散热铜箔面积或降低 Vout 压差
结论: 结温 1165.0 °C 超过上限 125.0 °C，需降流或换 DC-DC
判定: 不通过
```

**I2C 上拉**（3.3 V / 200 pF / tr ≤ 300 ns）：

```
· 上限 Rp_max = tr/(0.8473×Cbus) = 1770.3 Ω
· 下限 Rp_min = (Vdd-Vol)/Iol = (3.3-0.4)/3.0 mA = 966.7 Ω
· 推荐标称值（E24）：1500 Ω（区间内可选：[1000, 1200, 1500]）
```

**CAN 位定时**（42 MHz / 500 kbps）：

```
· BS1 = 73 tq，BS2 = 10 tq（SYNC 固定 1 tq）
· 采样点 = (1+BS1)/(1+BS1+BS2) = 88.1%（目标 87.5%）
· 实际波特率 = 500000.0 bps，误差 +0.000%
```

**BOM 校验**（示例板）：

```
21 个位号 / 32 个器件（不含 DNP）· 0 error · 1 warning
```

**设计评审**（示例回答）：

```
检查项总数：33
通过：27　未通过：4　不适用：2　未检查：0
是否具备投板条件：否

❌ critical 未通过项（阻塞投板）
- IF-03 CAN 位定时采样点是否接近 87.5%，两端是否各 120 Ω？
    - 备注：CAN 支线长度 2.5 m 超过 500 kbps 建议上限 0.6 m，需缩短或降速
```

---

## 6. 开发过程中被测试抓出来的问题

| # | 问题 | 定位方式 | 修复 |
|---|---|---|---|
| 1 | **CLI 在 Windows 上直接崩**：计算推导里用了数学减号 `−`（U+2212），控制台 GBK 编码无法输出 | 冒烟测试抛 `UnicodeEncodeError` | 统一换 ASCII 减号，并在 `main()` 里把 stdout/stderr 重配为 UTF-8（`errors="replace"` 兜底） |
| 2 | **位号格式规则会被误判**：测试里以为 `RES1` 非法，实际它符合"字母+数字"规范 | 单测 `test_bad_ref_format` 失败 | 规则保持不变（`RES1` 合法），把用例改成真正非法的 `1R` / `R-1` / `R 1`，并补一条"不得误报 RES1"的断言 |

> 第 2 条的价值在于：**规则没写错，是测试的预期写错了** —— 这类失败如果不深究，
> 很容易把正确的实现"修坏"。

---

## 7. 边界说明（重要）

- 本项目是**自建工具与实践**，**未在企业正式项目中投入使用**
- 计算基于**通用工程公式与经验取值**，**不替代器件手册、仿真与实测**：
  · 结温估算用单一 `θJA`，未考虑铜箔面积、气流与多热源耦合
  · 抗混叠只算一阶 RC，未含运放输出阻抗与 ADC 采样保持效应
  · CAN 支线长度上限用的是常见经验表，不同收发器与拓扑会有差异
- **不包含**：EMC/EMI 仿真与预测试、SI/PI 分析、热仿真、
  原理图/PCB 文件的自动解析（当前 BOM 以 JSON 输入）
- 评审清单是**通用条目**，不同产品（工业/消费/车规）需按标准补充裁剪

**下一步可做**：解析 KiCad/Altium 网表自动生成 BOM 与连接检查；
把评审清单做成可配置的 YAML 规则集；增加热仿真与降额计算；
把 `calc` 接入 CI 做"设计参数门禁"。

---

## 8. 许可

MIT
