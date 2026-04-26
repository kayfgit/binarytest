"""
sort_decompiled.py

Upward-compiled from: sort_bin (Linux x86_64 ELF, 493 bytes)
Source of Truth: Binary at entry point 0x400078

Mirrors exact register state, stack layout, sorting network topology,
and CMOV (conditional move) behavior from the original machine code.
"""

import sys
import os

# ============================================================
# CPU STATE MODEL
# ============================================================

rax = 0
rdi = 0
rsi = 0
rdx = 0
r8  = 0
r9  = 0
r10 = 0
r11 = 0

# 32-byte stack frame:
#   [0..3]    prompt scratchpad (rewritten 4 times)
#   [8..9]    digit 1 input buffer
#   [10..11]  digit 2 input buffer
#   [12..13]  digit 3 input buffer
#   [14..15]  digit 4 input buffer
#   [16..23]  output buffer (8 bytes: "X X X X\n")
stack = bytearray(32)


# ============================================================
# SYSCALL DISPATCH
# ============================================================

def syscall(num, fd, buf, count):
    if num == 1:    # sys_write
        sys.stdout.buffer.write(bytes(buf[:count]))
        sys.stdout.buffer.flush()
    elif num == 0:  # sys_read
        data = os.read(fd, count)
        for i, b in enumerate(data):
            buf[i] = b
    elif num == 60: # sys_exit
        sys.exit(fd)


# ============================================================
# COMPARE-AND-SWAP (CMOV EMULATION)
#
# Binary pattern per CAS:
#   mov eax, rXd       ; save first operand
#   cmp rXd, rYd       ; set flags: rX - rY
#   cmovg rXd, rYd     ; if rX > rY: rX = rY (gets min)
#   cmovg rYd, eax     ; if rX > rY: rY = saved (gets max)
#
# CMOV does NOT modify flags -- both cmovg read the same cmp result.
# This is the key insight: branchless swap in 4 instructions, 14 bytes.
# ============================================================

def cas(a, b):
    """
    Compare-and-swap: returns (min, max).
    Models the 4-instruction CMOV sequence exactly.
    """
    saved = a           # mov eax, rXd
    greater = (a > b)   # cmp rXd, rYd  (flags: SF, OF, ZF)
    if greater:         # cmovg condition: SF == OF and ZF == 0
        a = b           # cmovg rXd, rYd
    if greater:         # same flags -- cmovg doesn't modify them
        b = saved       # cmovg rYd, eax
    return a, b


# ============================================================
# PROGRAM ENTRY -- Virtual Address 0x400078
# ============================================================

def _start():
    global rax, rdi, rsi, rdx, r8, r9, r10, r11, stack

    # ----------------------------------------------------------
    # 0x0078: sub rsp, 32
    # ----------------------------------------------------------
    rsp = 0

    # ==========================================================
    # I/O PHASE: 4 prompt-read cycles
    # The prompt scratchpad at [rsp+0..3] is overwritten each time.
    # Only the first byte changes: 0x31='1', 0x32='2', 0x33='3', 0x34='4'
    # ==========================================================

    read_offsets = [8, 10, 12, 14]
    prompt_chars = [0x31, 0x32, 0x33, 0x34]  # '1', '2', '3', '4'

    for i in range(4):
        # 0x007C/0x00A7/0x00D2/0x00FD: mov dword [rsp], prompt
        stack[0] = prompt_chars[i]
        stack[1] = 0x3A  # ':'
        stack[2] = 0x20  # ' '
        stack[3] = 0x00  # NUL

        # mov eax,1 / mov edi,1 / mov rsi,rsp / mov edx,3 / syscall
        rax = 1
        rdi = 1
        rsi = rsp
        rdx = 3
        syscall(rax, rdi, memoryview(stack)[rsi:], rdx)

        # xor eax,eax / xor edi,edi / lea rsi,[rsp+N] / mov edx,2 / syscall
        rax = 0
        rdi = 0
        rsi = rsp + read_offsets[i]
        rdx = 2
        syscall(rax, rdi, memoryview(stack)[rsi:], rdx)

    # ==========================================================
    # LOAD & CONVERT PHASE (0x0128 - 0x014F)
    # movzx rNd, byte [rsp+offset]  ; zero-extend load
    # sub rNb, 0x30                 ; ASCII -> integer
    # ==========================================================

    # 0x0128: movzx r8d, byte [rsp+8]
    # 0x012E: sub r8b, 0x30
    r8 = (stack[rsp + 8] & 0xFF) - 0x30

    # 0x0132: movzx r9d, byte [rsp+10]
    # 0x0138: sub r9b, 0x30
    r9 = (stack[rsp + 10] & 0xFF) - 0x30

    # 0x013C: movzx r10d, byte [rsp+12]
    # 0x0142: sub r10b, 0x30
    r10 = (stack[rsp + 12] & 0xFF) - 0x30

    # 0x0146: movzx r11d, byte [rsp+14]
    # 0x014C: sub r11b, 0x30
    r11 = (stack[rsp + 14] & 0xFF) - 0x30

    # ==========================================================
    # SORTING NETWORK (0x0150 - 0x0195)
    #
    # Optimal 4-element network: 5 compare-and-swap operations.
    # Uses CMOV (conditional move) -- ZERO branches in the sort.
    #
    # Network topology:
    #   Stage 1: CAS(0,1) CAS(2,3)   -- parallel pairs
    #   Stage 2: CAS(0,2) CAS(1,3)   -- cross pairs
    #   Stage 3: CAS(1,2)            -- final middle swap
    # ==========================================================

    # 0x0150: CAS(r8, r9)   -- sort positions 0,1
    r8, r9 = cas(r8, r9)

    # 0x015E: CAS(r10, r11) -- sort positions 2,3
    r10, r11 = cas(r10, r11)

    # 0x016C: CAS(r8, r10)  -- sort positions 0,2
    r8, r10 = cas(r8, r10)

    # 0x017A: CAS(r9, r11)  -- sort positions 1,3
    r9, r11 = cas(r9, r11)

    # 0x0188: CAS(r9, r10)  -- sort positions 1,2
    r9, r10 = cas(r9, r10)

    # After network: r8 <= r9 <= r10 <= r11

    # ==========================================================
    # OUTPUT PHASE (0x0196 - 0x01CD)
    # Convert integers back to ASCII, interleave with spaces
    # ==========================================================

    # 0x0196-0x01A5: add rNb, 0x30  (integer -> ASCII)
    r8  = (r8  + 0x30) & 0xFF
    r9  = (r9  + 0x30) & 0xFF
    r10 = (r10 + 0x30) & 0xFF
    r11 = (r11 + 0x30) & 0xFF

    # 0x01A6-0x01C9: build output at [rsp+16..23]
    stack[rsp + 16] = r8          # sorted[0]
    stack[rsp + 17] = 0x20        # space
    stack[rsp + 18] = r9          # sorted[1]
    stack[rsp + 19] = 0x20        # space
    stack[rsp + 20] = r10         # sorted[2]
    stack[rsp + 21] = 0x20        # space
    stack[rsp + 22] = r11         # sorted[3]
    stack[rsp + 23] = 0x0A        # newline

    # ==========================================================
    # WRITE RESULT (0x01CE - 0x01E3)
    # ==========================================================
    rax = 1
    rdi = 1
    rsi = rsp + 16
    rdx = 8
    syscall(rax, rdi, memoryview(stack)[rsi:], rdx)

    # ==========================================================
    # EXIT (0x01E4 - 0x01EC)
    # ==========================================================
    rax = 60
    rdi = 0
    syscall(rax, rdi, None, 0)


# ============================================================
# ELF LOADER SIMULATION
# ============================================================
if __name__ == "__main__":
    _start()
