#!/usr/bin/env python3
"""
Stopwatch SoC – Terasic DE2 (Altera Cyclone II EP2C35F672C6)
=============================================================
LiteX SoCCore  +  VexRiscv CPU  +  Stopwatch CSR peripheral

Sinh file:
  build/gateware/my_design.v   ← Verilog chứa toàn bộ CPU, RAM, ROM, Stopwatch
  build/gateware/de2_pins.qsf  ← Pin assignments cho Quartus II

Chỉ xuất Verilog, KHÔNG chạy Quartus (run=False).

Lệnh chạy:
    python3 soc.py

Sau đó dùng trong Quartus II:
  1. New Project Wizard → device EP2C35F672C6
  2. Add  build/gateware/my_design.v  vào project
  3. Source → Import Assignments → build/gateware/de2_pins.qsf
  4. Set top-level entity: 'stopwatch_soc'
  5. Compile → Program Device via JTAG

Testbench (Questa/ModelSim):
  • Mở Tools → Run Simulation Tool → RTL Simulation
  • Tìm dut → module stopwatch
  • Add mins_cnt, secs_cnt, ticks_cnt vào Wave
  • run 10ms → quan sát ticks_cnt tăng dần
"""

import os
import shutil

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.soc.integration.soc_core import SoCCore
from litex.soc.integration.builder  import Builder
from litex.build.altera              import AlteraPlatform
from litex.build.generic_platform   import Pins, IOStandard, Subsignal

from stopwatch import Stopwatch

# ─── Board constants ──────────────────────────────────────────────────────────
SYS_CLK_FREQ = int(50e6)   # Oscillator trên DE2: 50 MHz

# ─── I/O Resources (DE2 User Manual pin map) ────────────────────────────────
_io = [
    # Clock
    ("clk50",        0, Pins("N2"),  IOStandard("3.3-V LVTTL")),
    # Reset: KEY[0] active-low (nhấn = reset hệ thống)
    ("cpu_reset_n",  0, Pins("G26"), IOStandard("3.3-V LVTTL")),
    # UART (DB9 RS-232 qua MAX3241E trên DE2)
    ("serial", 0,
        Subsignal("tx", Pins("C25")),   # UART_TXD
        Subsignal("rx", Pins("B25")),   # UART_RXD
        IOStandard("3.3-V LVTTL"),
    ),
    # Push buttons KEY[1..3] active-low dùng cho Stopwatch
    ("user_btn", 0, Pins("N23"), IOStandard("3.3-V LVTTL")),  # KEY[1] → Start
    ("user_btn", 1, Pins("P23"), IOStandard("3.3-V LVTTL")),  # KEY[2] → Pause
    ("user_btn", 2, Pins("W26"), IOStandard("3.3-V LVTTL")),  # KEY[3] → Reset
    # Red LEDs LEDR[9:0]
    ("user_led", 0, Pins("AE23 AF23 AB21 AC22 AD22 AD23 AD21 AC21 AA14 Y13"),
        IOStandard("3.3-V LVTTL")),
    # 7-segment displays: HEX0..HEX5 (active-low, common-anode)
    ("hex", 0, Pins("AF10 AB12 AC12 AD11 AE11 V14 V13"),   IOStandard("3.3-V LVTTL")),
    ("hex", 1, Pins("V20 V21 W21 Y22 AA24 AA23 AB24"),     IOStandard("3.3-V LVTTL")),
    ("hex", 2, Pins("AB23 V22 AC25 AC26 AB26 AB25 Y24"),   IOStandard("3.3-V LVTTL")),
    ("hex", 3, Pins("Y23 AA25 AA26 Y26 Y25 U22 W24"),      IOStandard("3.3-V LVTTL")),
    ("hex", 4, Pins("U9 U1 U2 T4 R7 R6 T3"),               IOStandard("3.3-V LVTTL")),
    ("hex", 5, Pins("T2 P6 P7 T9 R5 R4 R3"),               IOStandard("3.3-V LVTTL")),
]

# ─── Platform ──────────────────────────────────────────────────────────────
class DE2Platform(AlteraPlatform):
    """Terasic DE2 – Altera Cyclone II EP2C35F672C6"""
    default_clk_name   = "clk50"
    default_clk_period = 1e9 / 50e6   # 20 ns → 50 MHz

    def __init__(self):
        AlteraPlatform.__init__(self, "EP2C35F672C6", _io)
        self.add_platform_command('set_global_assignment -name FAMILY "Cyclone II"')
        self.add_platform_command('set_global_assignment -name DEVICE EP2C35F672C6')


# ─── CRG (Clock & Reset Generator) với Cyclone II ALTPLL ─────────────────────
class CRG(Module):
    """
    Sinh clock domain 'sys' từ oscillator 50 MHz trên DE2 qua ALTPLL.

    Cấu hình ALTPLL:
      inclk0  = 50 MHz   (20 000 ps)
      VCO     = 100 MHz  (multiply×2)
      clk[0]  = 50 MHz   (divide÷2)   → sys domain

    Cyclone II yêu cầu VCO ≥ 100 MHz, nên dùng ×2/÷2 cho 50 MHz output.
    Để thay đổi sys_clk_freq, điều chỉnh clk0_multiply_by / clk0_divide_by.
    """
    def __init__(self, platform, sys_clk_freq=SYS_CLK_FREQ):
        self.rst = Signal()   # soft-reset input từ SoC

        # Giữ reference để dùng trong AsyncResetSynchronizer
        self._cd_sys = ClockDomain("sys")
        self.clock_domains += self._cd_sys

        clk50  = platform.request("clk50")
        rst_n  = platform.request("cpu_reset_n")

        pll_locked = Signal()
        pll_clk0   = Signal()

        # ALTPLL: 50 MHz in → 50 MHz out  (VCO = 100 MHz)
        # inclk0_input_frequency tính bằng picoseconds: 1/50 MHz = 20 000 ps
        self.specials += Instance(
            "altpll",
            p_intended_device_family = "Cyclone II",
            p_operation_mode         = "NORMAL",
            p_pll_type               = "AUTO",
            p_compensate_clock       = "CLK0",
            p_inclk0_input_frequency = 20_000,    # 20 000 ps = 50 MHz
            p_clk0_multiply_by       = 2,          # VCO = 50×2 = 100 MHz
            p_clk0_divide_by         = 2,          # clk0 = 100÷2 = 50 MHz
            p_clk0_duty_cycle        = 50,
            p_clk0_phase_shift       = "0",
            # inclk là bus 2-bit [1:0]; dùng inclk[0] = clk50
            i_inclk  = Cat(clk50, Signal()),
            # areset active-high: reset PLL khi KEY[0] nhấn
            i_areset = ~rst_n,
            # clk là bus 6-bit [5:0]; chỉ quan tâm clk[0]
            o_clk    = Cat(pll_clk0,
                           Signal(), Signal(), Signal(),
                           Signal(), Signal()),
            o_locked = pll_locked,
        )

        # Gán clock và reset đồng bộ cho domain sys
        self.comb += ClockSignal("sys").eq(pll_clk0)
        self.specials += AsyncResetSynchronizer(
            self._cd_sys,
            ~pll_locked | self.rst,
        )


# ─── 7-segment helpers ──────────────────────────────────────────────────────
# Bảng mã 7-seg active-low, common-anode (DE2)
# bit: 6=g  5=f  4=e  3=d  2=c  1=b  0=a
SEG7 = {
    0: 0b1000000,  1: 0b1111001,  2: 0b0100100,  3: 0b0110000,
    4: 0b0011001,  5: 0b0010010,  6: 0b0000010,  7: 0b1111000,
    8: 0b0000000,  9: 0b0010000,
}

def seg7_case(val_sig, seg_out):
    cases = {d: seg_out.eq(SEG7[d]) for d in range(10)}
    cases["default"] = seg_out.eq(0b1111111)   # tắt tất cả
    return Case(val_sig, cases)

def bcd_split(module, val_sig, max_val, tens_out, ones_out):
    cases = {i: [tens_out.eq(i // 10), ones_out.eq(i % 10)]
             for i in range(max_val + 1)}
    module.comb += Case(val_sig, cases)


# ─── SoC ────────────────────────────────────────────────────────────────────
class StopwatchSoC(SoCCore):
    """
    LiteX SoC chứa:
      • VexRiscv (RV32IM) CPU
      • BIOS ROM  32 KiB  (integrated, sinh bởi LiteX)
      • Main RAM  32 KiB  (integrated SRAM)
      • UART      (RS-232 trên DE2)
      • Stopwatch (CSR peripheral từ stopwatch.py)
        CSR map ví dụ:
          0x8_2000  stopwatch_start   (W)
          0x8_2004  stopwatch_pause   (W)
          0x8_2008  stopwatch_stop    (W)
          0x8_200C  stopwatch_reset   (W)
          0x8_2010  stopwatch_minutes (R)
          0x8_2014  stopwatch_seconds (R)
          0x8_2018  stopwatch_ticks   (R)
      • 7-segment HEX0–HEX5 + LEDR[0] nối trực tiếp với CSR status
    """

    def __init__(self, platform, sys_clk_freq=SYS_CLK_FREQ):
        # ── LiteX SoCCore ────────────────────────────────────────────────
        SoCCore.__init__(
            self,
            platform                   = platform,
            clk_freq                   = sys_clk_freq,
            integrated_rom_size        = 0x8000,   # 32 KiB BIOS ROM
            integrated_main_ram_size   = 0x8000,   # 32 KiB RAM
            with_uart                  = True,
            uart_name                  = "serial",
            with_ethernet              = False,
            ident                      = "Stopwatch SoC – DE2 Cyclone II",
            ident_version              = True,
        )

        # ── CRG: ALTPLL 50 MHz → sys domain ─────────────────────────────
        self.submodules.crg = CRG(platform, sys_clk_freq)

        # ── Stopwatch CSR peripheral ─────────────────────────────────────
        self.submodules.stopwatch = Stopwatch(sys_clk_freq)
        self.add_csr("stopwatch")

        # ── Hardware buttons (KEY[1..3] active-low) ──────────────────────
        # Nếu nhấn KEY, override CSR storage = 1 (firmware cũng có thể ghi)
        btn_start = platform.request("user_btn", 0)   # KEY[1] → Start
        btn_pause = platform.request("user_btn", 1)   # KEY[2] → Pause
        btn_reset = platform.request("user_btn", 2)   # KEY[3] → Reset

        # Drive hardware input signals (active-high = button pressed = KEY active-low inverted)
        # Do NOT drive .storage directly — that net is already driven by the CSR bus
        self.comb += [
            self.stopwatch.hw_start.eq(~btn_start),
            self.stopwatch.hw_pause.eq(~btn_pause),
            self.stopwatch.hw_reset.eq(~btn_reset),
        ]

        # ── 7-segment HEX0–HEX5 ─────────────────────────────────────────
        sw = self.stopwatch
        t_tens = Signal(4); t_ones = Signal(4)
        s_tens = Signal(4); s_ones = Signal(4)
        m_tens = Signal(4); m_ones = Signal(4)

        bcd_split(self, sw.ticks.status,   99, t_tens, t_ones)
        bcd_split(self, sw.seconds.status, 59, s_tens, s_ones)
        bcd_split(self, sw.minutes.status, 59, m_tens, m_ones)

        for idx, bcd_val in enumerate([t_ones, t_tens, s_ones, s_tens, m_ones, m_tens]):
            pad     = platform.request("hex", idx)
            seg_sig = Signal(7, name=f"hex{idx}_seg")
            self.comb += [
                seg7_case(bcd_val, seg_sig),
                pad.eq(seg_sig),
            ]

        # ── LEDR[0] = ticks LSB (bật tắt mỗi 0.01 giây = running indicator)
        led_pad = platform.request("user_led")
        self.comb += led_pad[0].eq(sw.ticks.status[0])


# ─── Quartus II pin assignment bổ sung ──────────────────────────────────────
DE2_QSF_EXTRA = """\

# ── Thêm vào / ghi đè file .qsf do LiteX sinh ra ────────────────────────
# ── Clock ───────────────────────────────────────────────────────────────
set_location_assignment PIN_N2   -to clk50

# ── Reset KEY[0] ────────────────────────────────────────────────────────
set_location_assignment PIN_G26  -to cpu_reset_n

# ── UART RS-232 ─────────────────────────────────────────────────────────
set_location_assignment PIN_C25  -to serial_tx
set_location_assignment PIN_B25  -to serial_rx

# ── User buttons KEY[1..3] ──────────────────────────────────────────────
set_location_assignment PIN_N23  -to user_btn_0
set_location_assignment PIN_P23  -to user_btn_1
set_location_assignment PIN_W26  -to user_btn_2

# ── Red LEDs ─────────────────────────────────────────────────────────────
set_location_assignment PIN_AE23 -to user_led[0]
set_location_assignment PIN_AF23 -to user_led[1]
set_location_assignment PIN_AB21 -to user_led[2]
set_location_assignment PIN_AC22 -to user_led[3]
set_location_assignment PIN_AD22 -to user_led[4]
set_location_assignment PIN_AD23 -to user_led[5]
set_location_assignment PIN_AD21 -to user_led[6]
set_location_assignment PIN_AC21 -to user_led[7]
set_location_assignment PIN_AA14 -to user_led[8]
set_location_assignment PIN_Y13  -to user_led[9]

# ── HEX0 (ticks ones) ────────────────────────────────────────────────────
set_location_assignment PIN_AF10 -to hex0[0]
set_location_assignment PIN_AB12 -to hex0[1]
set_location_assignment PIN_AC12 -to hex0[2]
set_location_assignment PIN_AD11 -to hex0[3]
set_location_assignment PIN_AE11 -to hex0[4]
set_location_assignment PIN_V14  -to hex0[5]
set_location_assignment PIN_V13  -to hex0[6]

# ── HEX1 (ticks tens) ────────────────────────────────────────────────────
set_location_assignment PIN_V20  -to hex1[0]
set_location_assignment PIN_V21  -to hex1[1]
set_location_assignment PIN_W21  -to hex1[2]
set_location_assignment PIN_Y22  -to hex1[3]
set_location_assignment PIN_AA24 -to hex1[4]
set_location_assignment PIN_AA23 -to hex1[5]
set_location_assignment PIN_AB24 -to hex1[6]

# ── HEX2 (seconds ones) ──────────────────────────────────────────────────
set_location_assignment PIN_AB23 -to hex2[0]
set_location_assignment PIN_V22  -to hex2[1]
set_location_assignment PIN_AC25 -to hex2[2]
set_location_assignment PIN_AC26 -to hex2[3]
set_location_assignment PIN_AB26 -to hex2[4]
set_location_assignment PIN_AB25 -to hex2[5]
set_location_assignment PIN_Y24  -to hex2[6]

# ── HEX3 (seconds tens) ──────────────────────────────────────────────────
set_location_assignment PIN_Y23  -to hex3[0]
set_location_assignment PIN_AA25 -to hex3[1]
set_location_assignment PIN_AA26 -to hex3[2]
set_location_assignment PIN_Y26  -to hex3[3]
set_location_assignment PIN_Y25  -to hex3[4]
set_location_assignment PIN_U22  -to hex3[5]
set_location_assignment PIN_W24  -to hex3[6]

# ── HEX4 (minutes ones) ──────────────────────────────────────────────────
set_location_assignment PIN_U9   -to hex4[0]
set_location_assignment PIN_U1   -to hex4[1]
set_location_assignment PIN_U2   -to hex4[2]
set_location_assignment PIN_T4   -to hex4[3]
set_location_assignment PIN_R7   -to hex4[4]
set_location_assignment PIN_R6   -to hex4[5]
set_location_assignment PIN_T3   -to hex4[6]

# ── HEX5 (minutes tens) ──────────────────────────────────────────────────
set_location_assignment PIN_T2   -to hex5[0]
set_location_assignment PIN_P6   -to hex5[1]
set_location_assignment PIN_P7   -to hex5[2]
set_location_assignment PIN_T9   -to hex5[3]
set_location_assignment PIN_R5   -to hex5[4]
set_location_assignment PIN_R4   -to hex5[5]
set_location_assignment PIN_R3   -to hex5[6]

# ── I/O Standard ────────────────────────────────────────────────────────
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to clk50
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to cpu_reset_n
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to serial_tx
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to serial_rx
"""


# ─── Build ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    platform = DE2Platform()
    soc      = StopwatchSoC(platform, sys_clk_freq=SYS_CLK_FREQ)

    # Builder: ghi output vào build/, KHÔNG gọi Quartus (run=False)
    builder = Builder(
        soc,
        output_dir       = "build",
        compile_software = False,   # không build firmware C
        compile_gateware = False,   # không chạy quartus_sh
    )
    builder.build(run=False)

    # ── Tìm file Verilog vừa sinh và đổi tên thành my_design.v ─────────────
    gateware_dir = os.path.join("build", "gateware")
    os.makedirs(gateware_dir, exist_ok=True)

    candidates = [
        os.path.join(gateware_dir, "stopwatch_soc.v"),
        os.path.join(gateware_dir, "de2.v"),
        os.path.join(gateware_dir, "top.v"),
    ]
    src_v = None
    for c in candidates:
        if os.path.exists(c):
            src_v = c
            break

    # Fallback: lấy file .v mới nhất trong thư mục
    if src_v is None:
        vs = [f for f in os.listdir(gateware_dir) if f.endswith(".v")]
        if vs:
            vs.sort(
                key=lambda f: os.path.getmtime(os.path.join(gateware_dir, f)),
                reverse=True,
            )
            src_v = os.path.join(gateware_dir, vs[0])

    dst_v = os.path.join(gateware_dir, "my_design.v")
    if src_v and os.path.abspath(src_v) != os.path.abspath(dst_v):
        shutil.copy2(src_v, dst_v)
        print(f">>> Verilog  : {dst_v}  (copy từ {os.path.basename(src_v)})")
    elif os.path.exists(dst_v):
        print(f">>> Verilog  : {dst_v}")
    else:
        print("!!! Không tìm thấy Verilog output – kiểm tra build/gateware/")

    # ── Ghi pin QSF ──────────────────────────────────────────────────────────
    qsf_path = os.path.join(gateware_dir, "de2_pins.qsf")
    with open(qsf_path, "a") as f:
        f.write(DE2_QSF_EXTRA)
    print(f">>> QSF pins : {qsf_path}")

    # ── Hướng dẫn ────────────────────────────────────────────────────────────
    print()
    print("=" * 62)
    print("  Dùng trong Quartus II:")
    print("=" * 62)
    print("  1. New Project Wizard → device: EP2C35F672C6")
    print("  2. Add  build/gateware/my_design.v")
    print("  3. Source → Import Assignments → build/gateware/de2_pins.qsf")
    print("  4. Top-level entity: 'stopwatch_soc'")
    print("  5. Compile → Program Device via JTAG")
    print()
    print("  Testbench (Questa / ModelSim):")
    print("  • Tools → Run Simulation Tool → RTL Simulation")
    print("  • Tìm dut → stopwatch module")
    print("  • Add  mins_cnt, secs_cnt, ticks_cnt  vào Wave")
    print("  • Lệnh: run 10ms   → quan sát ticks_cnt tăng dần")
    print("=" * 62)