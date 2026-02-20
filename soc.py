from migen import *
from litex.soc.integration.soc_core import SoCCore
from litex.soc.integration.builder import Builder
from litex.build.generic_platform import *
from litex.build.sim import SimPlatform

from stopwatch import Stopwatch

# ── IO pads cho SimPlatform ────────────────────────────────────────────────
_io = [
    ("sys_clk", 0, Pins(1)),
    ("sys_rst", 0, Pins(1)),
]

# ── Clock domain đơn giản cho simulation ───────────────────────────────────
class CRG(Module):
    def __init__(self, platform):
        self.clock_domains.cd_sys = ClockDomain()
        self.comb += [
            self.cd_sys.clk.eq(platform.request("sys_clk")),
            self.cd_sys.rst.eq(platform.request("sys_rst")),
        ]

class MySoC(SoCCore):
    def __init__(self):
        # Tạo platform giả lập
        platform = SimPlatform("sim", _io)

        # Cấu hình SoC cơ bản
        SoCCore.__init__(self, 
            platform=platform, 
            cpu_type="vexriscv",
            clk_freq=int(1e6),          # 1MHz for fast simulation
            uart_name="stub",           # Stub UART (no physical pin needed)
            integrated_rom_size=0x8000,
            integrated_main_ram_size=0x4000
        )

        # Thêm clock domain cho simulation
        self.submodules.crg = CRG(platform)

        # Gắn module Stopwatch (truyền tần số clock để chia tick đúng)
        self.submodules.stopwatch = Stopwatch(sys_clk_freq=int(1e6))
        self.add_csr("stopwatch")

if __name__ == "__main__":
    soc = MySoC()
    builder = Builder(soc, output_dir="build", csr_csv="csr.csv")
    # run=False: chỉ generate RTL + CSR headers, không chạy Verilator simulation
    builder.build(run=False)