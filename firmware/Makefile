CROSS = riscv64-unknown-elf-
CC    = $(CROSS)gcc
OBJCOPY = $(CROSS)objcopy
SIZE    = $(CROSS)size

SOC_BUILD  = ../build/software
LITEX_BASE = $(shell python3 -c "import litex,os; print(os.path.dirname(litex.__file__))")

CFLAGS = -march=rv32i -mabi=ilp32 -O2 -Wall -nostdlib -nostartfiles \
         -I $(SOC_BUILD)/include \
         -I $(LITEX_BASE)/soc/software/include \
         -I $(LITEX_BASE)/soc/cores/cpu/vexriscv

all: stopwatch.elf stopwatch.bin

stopwatch.elf: main.c
	$(CC) $(CFLAGS) $< -o $@
	$(SIZE) $@

stopwatch.bin: stopwatch.elf
	$(OBJCOPY) -O binary $< $@
	@echo "Binary size: $$(wc -c < $@) bytes"

clean:
	rm -f stopwatch.elf stopwatch.bin

.PHONY: all clean
