"""hwdk — 嵌入式硬件设计与验证工具集

把硬件设计里**可计算、可校验、可沉淀**的部分工具化：

  calc    电源树（LDO/DC-DC 功耗与结温）、信号链（运放/ADC/抗混叠）、
          接口电路（I2C 上拉、UART 波特率误差、CAN 位定时与终端、SPI 时钟、USB 匹配）
  bom     BOM 校验（位号重复/封装缺失/参数缺失/单点失效料）与导出
  review  硬件设计评审清单（电源/信号链/接口/EMC-EMI/DFM-DFT/文档）
  report  硬件测试方案与测试报告生成

零第三方依赖；所有计算都返回**带推导步骤**的结果，可直接作为设计计算书归档。

快速开始：
    python -m hwdk checklist -o checklist.md
    python -m hwdk calc ldo --vin 24 --vout 5 --iout 1.0
    python -m hwdk calc i2c --vdd 3.3 --cbus 200
    python -m hwdk bom examples/bom_sample.json -o bom_report.md
"""
from .bom import (BomIssue, BomItem, BomReport, to_csv, to_markdown,  # noqa: F401
                  validate_bom)
from .calc import (CalcResult, adc_resolution, antialias_filter,      # noqa: F401
                   can_bit_timing, can_termination, dcdc_power,
                   decoupling_caps, i2c_pullup, ldo_power, opamp_gain,
                   power_tree, spi_max_clock, uart_baud_error,
                   usb_series_resistor)
from .review import (CHECKLIST, CheckItem, evaluate_review,           # noqa: F401
                     render_checklist, render_review, render_test_plan,
                     render_test_report)

__version__ = "1.0.0"
__all__ = [
    "CalcResult", "ldo_power", "dcdc_power", "power_tree", "decoupling_caps",
    "opamp_gain", "adc_resolution", "antialias_filter",
    "i2c_pullup", "uart_baud_error", "can_bit_timing", "can_termination",
    "spi_max_clock", "usb_series_resistor",
    "BomItem", "BomIssue", "BomReport", "validate_bom", "to_csv", "to_markdown",
    "CheckItem", "CHECKLIST", "evaluate_review", "render_checklist",
    "render_review", "render_test_plan", "render_test_report",
    "__version__",
]
