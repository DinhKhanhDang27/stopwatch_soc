/*
 * Stopwatch Firmware  —  phút:giây:tích-tắc
 *
 * Cách biên dịch:
 *   riscv64-unknown-elf-gcc -march=rv32i -mabi=ilp32 \
 *       -I../build/software/include \
 *       -nostartfiles -T../build/software/include/generated/regions.ld \
 *       main.c -o stopwatch.elf
 *
 * Điều khiển qua CSR registers (do litex tự sinh ra trong csr.h):
 *   stopwatch_start_write(1) / (0)  → bắt đầu / xác nhận
 *   stopwatch_stop_write(1)  / (0)  → dừng
 *   stopwatch_reset_write(1) / (0)  → reset
 *   stopwatch_minutes_read()        → đọc phút
 *   stopwatch_seconds_read()        → đọc giây
 *   stopwatch_ticks_read()          → đọc tích-tắc (1/100 giây)
 */

#include <generated/csr.h>
#include <generated/mem.h>

/* ─── Cấu hình bộ nhớ lap ────────────────────────────────────────────────── */
#define MAX_LAPS        16
/* Mỗi lap lưu 3 byte: minutes, seconds, ticks */
#define LAP_RECORD_SIZE  3

/* Con trỏ vào MAIN_RAM để lưu lap times */
volatile unsigned char *lap_mem = (volatile unsigned char *)MAIN_RAM_BASE;

static int lap_count = 0;

/* ─── Hàm trợ giúp ──────────────────────────────────────────────────────── */

/* Ghi 1 lap vào RAM */
static void save_lap(void) {
    if (lap_count >= MAX_LAPS) return;          /* RAM đầy → bỏ qua */

    int base = lap_count * LAP_RECORD_SIZE;
    lap_mem[base + 0] = (unsigned char)stopwatch_minutes_read();
    lap_mem[base + 1] = (unsigned char)stopwatch_seconds_read();
    lap_mem[base + 2] = (unsigned char)stopwatch_ticks_read();
    lap_count++;
}

/* Đọc 1 lap từ RAM */
static void read_lap(int index,
                     unsigned char *m,
                     unsigned char *s,
                     unsigned char *t) {
    if (index >= lap_count) { *m = *s = *t = 0; return; }
    int base = index * LAP_RECORD_SIZE;
    *m = lap_mem[base + 0];
    *s = lap_mem[base + 1];
    *t = lap_mem[base + 2];
}

/* Xuống dòng nhỏ (busy-wait, không cần interrupt) */
static void delay_ms(volatile unsigned int ms) {
    /* Ước tính 1000 chu kỳ ≈ 1 ms @ 1 MHz, tuỳ chỉnh theo clk_freq thực */
    while (ms--) {
        volatile unsigned int d = 1000;
        while (d--);
    }
}

/* ─── main ──────────────────────────────────────────────────────────────── */
int main(void) {

    /* 1. Reset đồng hồ */
    stopwatch_reset_write(1);
    stopwatch_reset_write(0);

    /* 2. Bắt đầu đếm */
    stopwatch_start_write(1);
    stopwatch_start_write(0);

    /* 3. Vòng lặp chính: đọc + lưu lap mỗi 5 giây (5000 ms) */
    while (1) {
        delay_ms(5000);     /* đợi 5 giây */

        /* Lưu lap time */
        save_lap();

        /* Đọc lại lap vừa lưu để verify */
        unsigned char m, s, t;
        read_lap(lap_count - 1, &m, &s, &t);

        /*
         * Tại đây bạn có thể:
         *   - Ghi m/s/t ra GPIO → điều khiển 7-seg hoặc LED
         *   - Ghi ra UART (nếu có litex UART):
         *       printf("Lap %d: %02d:%02d.%02d\n", lap_count, m, s, t);
         *
         * Ví dụ điều khiển 7-seg qua seg_gpio (nếu đã add_csr("seg_gpio")):
         *   seg_gpio_out_write(encode_7seg(s));   // hiển thị giây
         */

        /* Nếu đã đủ MAX_LAPS lap → dừng đồng hồ */
        if (lap_count >= MAX_LAPS) {
            stopwatch_stop_write(1);
            stopwatch_stop_write(0);
            break;
        }
    }

    /* Treo CPU sau khi xong */
    while (1);
    return 0;
}
