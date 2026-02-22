"""
sim_stopwatch.py  —  Mô phỏng stopwatch thuần Python (không cần Verilator)

Chạy:
    source venv/bin/activate
    python3 sim_stopwatch.py

sys_clk_freq=200 → clk_per_tick = 200//100 = 2  (mỗi tick = 2 chu kỳ clock)
"""

from migen import *
from stopwatch import Stopwatch

SEPARATOR = "-" * 44


def read_time(dut):
    m = yield dut.minutes.status
    s = yield dut.seconds.status
    t = yield dut.ticks.status
    return m, s, t


def print_state(label, m, s, t):
    print(f"  [{label:<26}]  {m:02d}:{s:02d}.{t:02d}")


def testbench(dut, cycles_per_tick):

    def advance(n_ticks):
        for _ in range(n_ticks * cycles_per_tick):
            yield

    def pulse(sig):
        yield sig.eq(1)
        yield
        yield sig.eq(0)
        yield

    print(SEPARATOR)
    print("      STOPWATCH SIMULATION")
    print(SEPARATOR)

    # 1. RESET
    print("\n>> RESET")
    yield from pulse(dut.reset.storage)
    m, s, t = yield from read_time(dut)
    print_state("after RESET", m, s, t)
    assert (m, s, t) == (0, 0, 0), "FAIL: Reset khong ve 0!"
    print("  OK 00:00.00")

    # 2. START
    print("\n>> START  (dem 10 ticks)")
    yield from pulse(dut.start.storage)
    yield from advance(10)
    m, s, t = yield from read_time(dut)
    print_state("after 10 ticks", m, s, t)
    assert t >= 8, f"FAIL: ticks={t}"
    print(f"  OK dang chay, ticks={t}")

    # 3. PAUSE
    print("\n>> PAUSE")
    yield from pulse(dut.pause.storage)
    m_p, s_p, t_p = yield from read_time(dut)
    print_state("right after PAUSE", m_p, s_p, t_p)
    yield from advance(15)
    m2, s2, t2 = yield from read_time(dut)
    print_state("15 ticks later (paused)", m2, s2, t2)
    assert (m2, s2, t2) == (m_p, s_p, t_p), \
        f"FAIL: thoi gian thay doi khi PAUSE"
    print("  OK thoi gian dung yen")

    # 4. RESUME
    print("\n>> RESUME  (start lai, dem 8 ticks)")
    yield from pulse(dut.start.storage)
    yield from advance(8)
    m3, s3, t3 = yield from read_time(dut)
    print_state("after 8 more ticks", m3, s3, t3)
    assert (m3, s3, t3) != (m2, s2, t2), "FAIL: khong tang sau RESUME"
    print(f"  OK tiep tuc dem, ticks={t3}")

    # 5. STOP
    print("\n>> STOP")
    yield from pulse(dut.stop.storage)
    m_s, s_s, t_s = yield from read_time(dut)
    print_state("right after STOP", m_s, s_s, t_s)
    yield from advance(20)
    m4, s4, t4 = yield from read_time(dut)
    print_state("20 ticks later (stopped)", m4, s4, t4)
    assert (m4, s4, t4) == (m_s, s_s, t_s), \
        f"FAIL: thoi gian thay doi sau STOP"
    print("  OK thoi gian dung yen")

    # 6. START lai sau STOP
    print("\n>> START lai (dem 5 ticks)")
    yield from pulse(dut.start.storage)
    yield from advance(5)
    m5, s5, t5 = yield from read_time(dut)
    print_state("after 5 ticks", m5, s5, t5)
    assert (m5, s5, t5) != (m4, s4, t4), "FAIL: khong tang"
    print("  OK tiep tuc dem tu cho dung")

    # 7. RESET lan 2
    print("\n>> RESET lan 2")
    yield from pulse(dut.reset.storage)
    m6, s6, t6 = yield from read_time(dut)
    print_state("after RESET", m6, s6, t6)
    assert (m6, s6, t6) == (0, 0, 0), "FAIL: Reset lan 2 that bai!"
    print("  OK 00:00.00")

    print()
    print(SEPARATOR)
    print("  TAT CA TESTS PASSED")
    print(SEPARATOR)


if __name__ == "__main__":
    SIM_CLK_FREQ = 200          # clk_per_tick = 2 (tranh Signal(max=1))
    CYCLES_PER_TICK = SIM_CLK_FREQ // 100

    dut = Stopwatch(sys_clk_freq=SIM_CLK_FREQ)
    run_simulation(dut, testbench(dut, CYCLES_PER_TICK))
