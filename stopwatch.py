from migen import *
from litex.soc.interconnect.csr import *

class Stopwatch(Module, AutoCSR):
    """
    Stopwatch peripheral: phút:giây:tích-tắc (00:00:00 → 59:59:99)
    sys_clk_freq: tần số xung clock (Hz) dùng để chia ra 1 tick = 1/100 giây
    """
    def __init__(self, sys_clk_freq=int(1e6)):
        # ── CSR registers ────────────────────────────────────────────────────
        self.start   = CSRStorage(name="start")   # ghi 1 → bắt đầu chạy
        self.pause   = CSRStorage(name="pause")   # ghi 1 → tạm dừng (giữ nguyên thời gian)
        self.stop    = CSRStorage(name="stop")    # ghi 1 → dừng hẳn
        self.reset   = CSRStorage(name="reset")  # ghi 1 → reset về 0

        self.minutes = CSRStatus(8, name="minutes")  # phút (0–59)
        self.seconds = CSRStatus(8, name="seconds")  # giây (0–59)
        self.ticks   = CSRStatus(8, name="ticks")    # tích-tắc (0–99)

        # ── Internal signals ──────────────────────────────────────────────────
        running = Signal()

        # Số chu kỳ clock cho 1 tick (= 0.01 giây)
        clk_per_tick = max(1, int(sys_clk_freq // 100))

        clk_count  = Signal(max=clk_per_tick)  # bộ chia tần
        ticks_cnt  = Signal(7)  # 0–99
        secs_cnt   = Signal(6)  # 0–59
        mins_cnt   = Signal(6)  # 0–59

        # ── Sequential logic ─────────────────────────────────────────────────
        self.sync += [
            If(self.reset.storage,
                # reset ưu tiên tuyệt đối — dừng & xoá tất cả
                running.eq(0),
                clk_count.eq(0),
                ticks_cnt.eq(0),
                secs_cnt.eq(0),
                mins_cnt.eq(0),
            ).Else(
                # điều khiển start / pause / stop
                If(self.start.storage,
                    running.eq(1)
                ).Elif(self.pause.storage,
                    running.eq(0)   # đóng băng, giữ nguyên thời gian
                ).Elif(self.stop.storage,
                    running.eq(0)
                ),

                # đếm thời gian khi đang chạy
                If(running,
                    If(clk_count == clk_per_tick - 1,
                        clk_count.eq(0),
                        # tăng ticks
                        If(ticks_cnt == 99,
                            ticks_cnt.eq(0),
                            # tăng giây
                            If(secs_cnt == 59,
                                secs_cnt.eq(0),
                                # tăng phút (quay vòng sau 59)
                                If(mins_cnt == 59,
                                    mins_cnt.eq(0),
                                ).Else(
                                    mins_cnt.eq(mins_cnt + 1),
                                )
                            ).Else(
                                secs_cnt.eq(secs_cnt + 1),
                            )
                        ).Else(
                            ticks_cnt.eq(ticks_cnt + 1),
                        )
                    ).Else(
                        clk_count.eq(clk_count + 1),
                    )
                )
            )
        ]

        # ── Combinational output ─────────────────────────────────────────────
        self.comb += [
            self.ticks.status.eq(ticks_cnt),
            self.seconds.status.eq(secs_cnt),
            self.minutes.status.eq(mins_cnt),
        ]