# Stopwatch SoC

Đồng hồ đếm giờ **phút:giây:tích-tắc** thiết kế trên LiteX.

## Cấu trúc dự án

```
stopwatch_soc/
├── soc.py            ← Định nghĩa SoC (CPU + Bus + RAM + Stopwatch CSR)
├── stopwatch.py      ← Hardware peripheral stopwatch (Migen)
├── firmware/
│   ├── main.c        ← Firmware RISC-V (đọc CSR, lưu lap vào RAM)
│   └── Makefile      ← Build firmware
└── build/            ← Tự sinh bởi soc.py (gitignore)
    └── software/include/generated/
        ├── csr.h     ← CSR register functions (tự sinh)
        └── mem.h     ← Memory map (tự sinh)
```

## Thành phần SoC

| Thành phần | Mô tả |
|---|---|
| CPU | VexRiscv (RISC-V RV32I) |
| Bus | Wishbone 32-bit |
| ROM | 32KiB (BIOS) tại `0x00000000` |
| SRAM | 8KiB tại `0x10000000` |
| Main RAM | 16KiB tại `0x40000000` — lưu lap times |
| Stopwatch CSR | Peripheral tại `0xf0000000` |

## CSR Registers — Stopwatch

| Địa chỉ | Register | Hướng | Chức năng |
|---|---|---|---|
| `0xf0000000` | `stopwatch_start` | W | Ghi `1` → bắt đầu đếm |
| `0xf0000004` | `stopwatch_stop` | W | Ghi `1` → dừng |
| `0xf0000008` | `stopwatch_reset` | W | Ghi `1` → reset về 00:00:00 |
| `0xf000000c` | `stopwatch_minutes` | R | Phút hiện tại (0–59) |
| `0xf0000010` | `stopwatch_seconds` | R | Giây hiện tại (0–59) |
| `0xf0000014` | `stopwatch_ticks` | R | Tích-tắc hiện tại (0–99) |

## Cài đặt môi trường

```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-venv build-essential \
    verilator libevent-dev libjson-c-dev pkg-config \
    gcc-riscv64-unknown-elf

cd stopwatch_soc
python3 -m venv venv
source venv/bin/activate

pip install migen litex ninja meson
pip install git+https://github.com/litex-hub/pythondata-cpu-vexriscv.git
pip install git+https://github.com/litex-hub/pythondata-software-picolibc.git
pip install git+https://github.com/litex-hub/pythondata-software-compiler_rt.git
pip install git+https://github.com/litex-hub/pythondata-misc-tapcfg.git
```

## Build SoC (sinh CSR headers)

```bash
source venv/bin/activate
python3 soc.py
```

File sinh ra tại `build/software/include/generated/`:
- `csr.h` — CSR access functions cho firmware
- `mem.h` — Memory map constants (`MAIN_RAM_BASE`, ...)
- `csr.csv` — Bảng CSR (địa chỉ của từng register)

## Build Firmware

```bash
source venv/bin/activate
cd firmware
make
```

Kết quả: `firmware/stopwatch.elf`, `firmware/stopwatch.bin`

## Chức năng Firmware

1. **Reset** đồng hồ về `00:00.00`
2. **Start** đếm thời gian
3. Mỗi 5 giây: **lưu lap time** vào Main RAM (`0x40000000`)
4. Sau `MAX_LAPS = 16` laps: dừng tự động

**Lưu Lap trong RAM:**
```c
volatile unsigned char *lap_mem = (volatile unsigned char *)MAIN_RAM_BASE;
// lap[n] = { minutes, seconds, ticks }  (3 bytes mỗi lap)
```

## Team Workflow (Git)

```bash
git init
git add soc.py stopwatch.py firmware/
git commit -m "init: stopwatch soc"
git remote add origin <repo_url>
git push -u origin main
```

Branches:
- `main` — hardware (soc.py, stopwatch.py)
- `firmware` — firmware (main.c)
- `7seg` — 7-segment display driver
