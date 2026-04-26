"""
calc_decompiled.py

Upward-compiled from: calc_bin (Linux x86_64 ELF, 300 bytes)
Source of Truth: Binary at entry point 0x400078

This Python script mirrors the exact register state, stack layout,
and syscall sequence found in the original machine code. Each block
maps to a contiguous run of instructions at the noted virtual address.
"""

import sys
import os

# ============================================================
# CPU STATE MODEL
# Mirrors the x86_64 register file used by the binary.
# Only registers touched by the program are tracked.
# ============================================================

rax = 0
rcx = 0
rdi = 0
rsi = 0
rdx = 0
rsp = 0  # stack pointer (logical)

# The binary allocates a 32-byte stack frame.
# Layout derived from instruction operands:
#   [rsp+0  .. rsp+3]  : prompt buffer (4 bytes, overwritten twice)
#   [rsp+8  .. rsp+9]  : input buffer A (digit + newline)
#   [rsp+10 .. rsp+11] : input buffer B (digit + newline)
#   [rsp+12 .. rsp+14] : output buffer (up to 3 bytes)
stack = bytearray(32)


# ============================================================
# SYSCALL DISPATCH
# The binary uses three syscall numbers:
#   0  -> sys_read(fd, buf, count)
#   1  -> sys_write(fd, buf, count)
#   60 -> sys_exit(code)
# ============================================================

def syscall(rax_val, rdi_val, rsi_buf, rdx_val):
    """
    Dispatches a Linux x86_64 syscall.
    rax = syscall number
    rdi = first argument
    rsi_buf = pointer (here: bytes or bytearray slice)
    rdx = third argument (count)
    """
    if rax_val == 1:  # sys_write
        fd = rdi_val
        data = bytes(rsi_buf[:rdx_val])
        if fd == 1:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        elif fd == 2:
            sys.stderr.buffer.write(data)
            sys.stderr.buffer.flush()
        return rdx_val

    elif rax_val == 0:  # sys_read
        fd = rdi_val
        data = os.read(fd, rdx_val)
        for i, b in enumerate(data):
            rsi_buf[i] = b
        return len(data)

    elif rax_val == 60:  # sys_exit
        sys.exit(rdi_val)


# ============================================================
# PROGRAM ENTRY -- Virtual Address 0x400078
# Decompiled instruction-by-instruction from the binary.
# ============================================================

def _start():
    global rax, rcx, rdi, rsi, rdx, rsp, stack

    # ----------------------------------------------------------
    # 0x0078: sub rsp, 32
    # Allocate 32-byte stack frame
    # ----------------------------------------------------------
    rsp = 0  # base of our stack model

    # ----------------------------------------------------------
    # 0x007C: mov dword [rsp], 0x00203a41
    # Store "A: \0" at stack base (little-endian: 0x41='A', 0x3a=':', 0x20=' ', 0x00=NUL)
    # ----------------------------------------------------------
    stack[0] = 0x41  # 'A'
    stack[1] = 0x3A  # ':'
    stack[2] = 0x20  # ' '
    stack[3] = 0x00  # NUL

    # ----------------------------------------------------------
    # 0x0083: mov eax, 1          ; syscall number: sys_write
    # 0x0088: mov edi, 1          ; file descriptor: stdout
    # 0x008D: mov rsi, rsp        ; buffer: stack base (prompt)
    # 0x0090: mov edx, 3          ; count: 3 bytes
    # 0x0095: syscall
    # ----------------------------------------------------------
    rax = 1
    rdi = 1
    rsi = rsp
    rdx = 3
    syscall(rax, rdi, memoryview(stack)[rsi:], rdx)

    # ----------------------------------------------------------
    # 0x0097: xor eax, eax        ; syscall number: sys_read (0)
    # 0x0099: xor edi, edi        ; file descriptor: stdin (0)
    # 0x009B: lea rsi, [rsp+8]    ; buffer: stack offset 8
    # 0x00A0: mov edx, 2          ; count: 2 bytes (digit + newline)
    # 0x00A5: syscall
    # ----------------------------------------------------------
    rax = 0
    rdi = 0
    rsi = rsp + 8
    rdx = 2
    syscall(rax, rdi, memoryview(stack)[rsi:], rdx)

    # ----------------------------------------------------------
    # 0x00A7: mov dword [rsp], 0x00203a42
    # Overwrite prompt with "B: \0"
    # ----------------------------------------------------------
    stack[0] = 0x42  # 'B'
    stack[1] = 0x3A  # ':'
    stack[2] = 0x20  # ' '
    stack[3] = 0x00  # NUL

    # ----------------------------------------------------------
    # 0x00AE: mov eax, 1
    # 0x00B3: mov edi, 1
    # 0x00B8: mov rsi, rsp
    # 0x00BB: mov edx, 3
    # 0x00C0: syscall
    # ----------------------------------------------------------
    rax = 1
    rdi = 1
    rsi = rsp
    rdx = 3
    syscall(rax, rdi, memoryview(stack)[rsi:], rdx)

    # ----------------------------------------------------------
    # 0x00C2: xor eax, eax
    # 0x00C4: xor edi, edi
    # 0x00C6: lea rsi, [rsp+10]
    # 0x00CB: mov edx, 2
    # 0x00D0: syscall
    # ----------------------------------------------------------
    rax = 0
    rdi = 0
    rsi = rsp + 10
    rdx = 2
    syscall(rax, rdi, memoryview(stack)[rsi:], rdx)

    # ----------------------------------------------------------
    # ARITHMETIC BLOCK (0x00D2 - 0x00E5)
    # ----------------------------------------------------------
    # 0x00D2: movzx eax, byte [rsp+8]     ; load first digit (ASCII)
    rax = stack[rsp + 8] & 0xFF

    # 0x00D7: sub al, 0x30                ; ASCII '0' = 0x30 -> integer
    rax = (rax - 0x30) & 0xFF

    # 0x00D9: movzx ecx, byte [rsp+10]    ; load second digit (ASCII)
    rcx = stack[rsp + 10] & 0xFF

    # 0x00DE: sub cl, 0x30                ; ASCII -> integer
    rcx = (rcx - 0x30) & 0xFF

    # 0x00E1: add eax, ecx               ; sum
    rax = rax + rcx

    # ----------------------------------------------------------
    # BRANCH: 0x00E3 - 0x0111
    # 0x00E3: cmp eax, 10
    # 0x00E6: jl 0x102 (single_digit)
    # ----------------------------------------------------------
    if rax >= 10:
        # --- TWO-DIGIT PATH (0x00E8 - 0x0100) ---

        # 0x00E8: sub eax, 10
        rax = rax - 10

        # 0x00EB: add al, 0x30           ; ones digit -> ASCII
        rax = (rax + 0x30) & 0xFF

        # 0x00ED: mov byte [rsp+12], 0x31  ; tens place is always '1'
        stack[rsp + 12] = 0x31

        # 0x00F2: mov byte [rsp+13], al
        stack[rsp + 13] = rax & 0xFF

        # 0x00F6: mov byte [rsp+14], 0x0a  ; newline
        stack[rsp + 14] = 0x0A

        # 0x00FB: mov edx, 3
        rdx = 3

        # 0x0100: jmp 0x112 (print_result)
        # (fall through to print_result below)

    else:
        # --- SINGLE-DIGIT PATH (0x0102 - 0x0111) ---

        # 0x0102: add al, 0x30           ; integer -> ASCII
        rax = (rax + 0x30) & 0xFF

        # 0x0104: mov byte [rsp+12], al
        stack[rsp + 12] = rax & 0xFF

        # 0x0108: mov byte [rsp+13], 0x0a  ; newline
        stack[rsp + 13] = 0x0A

        # 0x010D: mov edx, 2
        rdx = 2

    # ----------------------------------------------------------
    # PRINT RESULT (0x0112 - 0x0122)
    # 0x0112: mov eax, 1
    # 0x0117: mov edi, 1
    # 0x011C: lea rsi, [rsp+12]
    # 0x0121: syscall
    # ----------------------------------------------------------
    rax = 1
    rdi = 1
    rsi = rsp + 12
    syscall(rax, rdi, memoryview(stack)[rsi:], rdx)

    # ----------------------------------------------------------
    # EXIT (0x0123 - 0x012B)
    # 0x0123: mov eax, 60         ; sys_exit
    # 0x0128: xor edi, edi        ; exit code 0
    # 0x012A: syscall
    # ----------------------------------------------------------
    rax = 60
    rdi = 0
    syscall(rax, rdi, None, 0)


# ============================================================
# ELF LOADER SIMULATION
# The kernel maps the PT_LOAD segment and jumps to e_entry.
# ============================================================
if __name__ == "__main__":
    _start()
