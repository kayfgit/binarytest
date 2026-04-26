"""
primes_decompiled.py

Upward-compiled from: primes_bin (Linux x86_64 ELF, 300 bytes)
Source of Truth: Binary at entry point 0x400078

Three alien tricks from the binary:
  1. Bit-packed sieve: 100 numbers encoded in two 64-bit registers
  2. BSF (Bit Scan Forward): hardware priority encoder extracts primes
  3. Magic-number multiply: replaces DIV for decimal conversion
"""

import sys
import os

# ============================================================
# CPU STATE MODEL
# ============================================================
rax = 0
rcx = 0
rdx = 0
rdi = 0
rsi = 0
r8  = 0
r9  = 0
r12 = 0

stack = bytearray(24)  # 16 bytes + 8 for call return addr simulation


# ============================================================
# SYSCALL DISPATCH
# ============================================================
def syscall(num, fd, buf, count):
    if num == 1:
        sys.stdout.buffer.write(bytes(buf[:count]))
        sys.stdout.buffer.flush()
    elif num == 60:
        sys.exit(fd)


# ============================================================
# BSF EMULATION (Bit Scan Forward)
#
# Hardware instruction: scans a 64-bit register from bit 0 upward,
# returns the index of the first set bit. Implemented in silicon
# as a priority encoder -- no loop, no iteration. One clock cycle
# to search 64 bits. Sets ZF if input is zero.
#
# There is no equivalent in Python. We simulate it with bit math.
# ============================================================
def bsf(value):
    """Returns (index_of_lowest_set_bit, zero_flag)."""
    if value == 0:
        return 0, True
    index = 0
    while (value >> index) & 1 == 0:
        index += 1
    return index, False


# ============================================================
# BTR EMULATION (Bit Test and Reset)
#
# Hardware instruction: tests bit N of a register, copies it to CF,
# then clears it. Atomic read-modify in one instruction.
# ============================================================
def btr(value, bit):
    """Returns value with bit cleared."""
    return value & ~(1 << bit)


# ============================================================
# MAGIC NUMBER DIVISION (Replacing DIV)
#
# The binary avoids the DIV instruction entirely. Instead of
# dividing by 10, it multiplies by the magic constant 0xCCCCCCCD
# and shifts right. This exploits fixed-point arithmetic:
#
#   0xCCCCCCCD / 2^35 ≈ 1/10
#
# So (n * 0xCCCCCCCD) >> 35 = n / 10 (for n < 1000).
#
# The binary splits this as:
#   mul ecx        -> edx:eax = n * magic  (edx gets upper 32 bits)
#   shr edx, 3     -> edx = (n * magic) >> 35
#
# This is 2 instructions, ~3 cycles. DIV is 1 instruction, ~30 cycles.
# ============================================================
def magic_div10(n):
    """Divide by 10 using multiply-and-shift. No division operator."""
    magic = 0xCCCCCCCD
    product = n * magic                  # mul ecx (64-bit result)
    upper32 = (product >> 32) & 0xFFFFFFFF  # edx = upper 32 bits
    quotient = upper32 >> 3              # shr edx, 3
    remainder = n - (quotient * 10)      # imul + sub
    return quotient, remainder


# ============================================================
# BIT-PACKED PRIME SIEVE
#
# The architect performed the Sieve of Eratosthenes at design time
# using bit-parallel ANDN operations on 64-bit values:
#
#   1. Start: all odd numbers + 2  (init = 0xAAAAAAAAAAAAAAACi)
#   2. ANDN with multiples-of-3 mask  (0x8208208208208200)
#   3. ANDN with multiples-of-5 mask  (0x0080000802000000)
#   4. ANDN with multiples-of-7 mask  (0x8002000800200000)
#
# Each ANDN clears an entire prime's composite family in ONE clock
# cycle across 64 numbers simultaneously. The traditional sieve
# processes composites one at a time.
#
# The result is baked into two 64-bit constants:
#   r8 = 0x28208A20A08A28AC  (primes 2-61, bit N set = N is prime)
#   r9 = 0x0000000202088288  (primes 67-97, bit N set = N+64 is prime)
# ============================================================

PRIME_MASK_LO = 0x28208A20A08A28AC   # primes in [0, 63]
PRIME_MASK_HI = 0x0000000202088288   # primes in [64, 100]


# ============================================================
# PRINT SUBROUTINE -- Virtual Address 0x4000C6
#
# Converts r12d to decimal ASCII using magic-number division,
# writes to stdout via syscall.
# ============================================================
def print_number():
    global rax, rcx, rdx, rdi, rsi, r12, stack

    # 0x00C6: mov eax, r12d
    rax = r12 & 0xFFFFFFFF

    # 0x00C9: mov ecx, 0xCCCCCCCD       ; magic constant for /10
    # 0x00CE: mul ecx                    ; edx:eax = r12d * magic
    # 0x00D0: shr edx, 3                ; edx = r12d / 10
    # 0x00D3: imul eax, edx, 10         ; eax = quotient * 10
    # 0x00D6: mov ecx, r12d
    # 0x00D9: sub ecx, eax              ; ecx = r12d % 10
    tens, ones = magic_div10(r12 & 0xFFFFFFFF)
    rdx = tens
    rcx = ones

    # 0x00DB: test edx, edx
    # 0x00DD: jz .single (0x109)
    if rdx != 0:
        # --- TWO-DIGIT PATH (0x00DF - 0x0108) ---

        # 0x00DF: add dl, 0x30
        # 0x00E2: add cl, 0x30
        rdx = (rdx + 0x30) & 0xFF
        rcx = (rcx + 0x30) & 0xFF

        # 0x00E5: mov [rsp+8], dl       ; tens digit
        # 0x00E9: mov [rsp+9], cl       ; ones digit
        # 0x00ED: mov byte [rsp+10], 0x0a
        stack[8] = rdx
        stack[9] = rcx
        stack[10] = 0x0A

        # 0x00F2-0x0106: write(1, rsp+8, 3)
        rax = 1; rdi = 1; rdx = 3
        syscall(rax, rdi, memoryview(stack)[8:], rdx)
    else:
        # --- SINGLE-DIGIT PATH (0x0109 - 0x012B) ---

        # 0x0109: add cl, 0x30
        rcx = (rcx + 0x30) & 0xFF

        # 0x010C: mov [rsp+8], cl
        # 0x0110: mov byte [rsp+9], 0x0a
        stack[8] = rcx
        stack[9] = 0x0A

        # 0x0115-0x0129: write(1, rsp+8, 2)
        rax = 1; rdi = 1; rdx = 2
        syscall(rax, rdi, memoryview(stack)[8:], rdx)

    # 0x0108/0x012B: ret
    return


# ============================================================
# PROGRAM ENTRY -- Virtual Address 0x400078
# ============================================================
def _start():
    global rax, rcx, rdx, rdi, rsi, r8, r9, r12

    # ----------------------------------------------------------
    # 0x0078: sub rsp, 16
    # ----------------------------------------------------------

    # ----------------------------------------------------------
    # SIEVE PHASE (0x007C - 0x008F)
    #
    # Load the bit-packed prime sieve into two registers.
    # Each bit position N that is set represents a prime number.
    # For r8: bit N = 1 means N is prime (range 0-63)
    # For r9: bit N = 1 means N+64 is prime (range 64-100)
    # ----------------------------------------------------------

    # 0x007C: mov r8, 0x28208A20A08A28AC
    r8 = PRIME_MASK_LO

    # 0x0086: mov r9, 0x0000000202088288
    r9 = PRIME_MASK_HI

    # ----------------------------------------------------------
    # EXTRACTION PHASE 1: Primes 2-61 (0x0090 - 0x00A3)
    #
    # BSF finds the lowest set bit (= smallest remaining prime).
    # BTR clears that bit so the next BSF finds the next prime.
    # This extracts primes in ascending order without a counter.
    # ----------------------------------------------------------

    # .loop_r8:
    while True:
        # 0x0090: bsf rcx, r8     ; find lowest set bit
        rcx, zf = bsf(r8)

        # 0x0094: jz .switch      ; if r8 == 0, all primes extracted
        if zf:
            break

        # 0x0096: btr r8, rcx     ; clear that bit
        r8 = btr(r8, rcx)

        # 0x009A: mov r12d, ecx   ; prime = bit position (0-63)
        r12 = rcx & 0xFFFFFFFF

        # 0x009D: call .print_num
        print_number()

        # 0x00A2: jmp .loop_r8

    # ----------------------------------------------------------
    # EXTRACTION PHASE 2: Primes 67-97 (0x00A4 - 0x00B8)
    #
    # Same BSF+BTR loop, but adds 64 to the bit position
    # to recover the actual prime number.
    # ----------------------------------------------------------

    # .loop_r9:
    while True:
        # 0x00A4: bsf rcx, r9
        rcx, zf = bsf(r9)

        # 0x00A8: jz .exit
        if zf:
            break

        # 0x00AA: btr r9, rcx
        r9 = btr(r9, rcx)

        # 0x00AE: lea r12d, [ecx+64]  ; prime = bit position + 64
        r12 = (rcx + 64) & 0xFFFFFFFF

        # 0x00B2: call .print_num
        print_number()

        # 0x00B7: jmp .loop_r9

    # ----------------------------------------------------------
    # EXIT (0x00B9 - 0x00C5)
    # ----------------------------------------------------------
    # 0x00B9: add rsp, 16
    # 0x00BD: mov eax, 60
    # 0x00C2: xor edi, edi
    # 0x00C4: syscall
    rax = 60
    rdi = 0
    syscall(rax, rdi, None, 0)


if __name__ == "__main__":
    _start()
