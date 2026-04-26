# Human Compiler -- Multi-Resolution Analysis

> Source of Truth: `sort_bin` (493 bytes, Linux x86_64 ELF)
> Sorting 4 single-digit numbers, ascending order.

---

# Level 10 -- The Elevator Pitch

A 493-byte program that reads four single-digit numbers from the keyboard and prints them sorted from smallest to largest. It runs directly on Linux with no libraries, no runtime, and no dependencies.

---

# Level 4 -- The Schematic

The program operates in four distinct phases:

**Phase 1: Input.** Four prompt-read cycles collect single-digit numbers. The prompt string is stored once on the stack and mutated in place between cycles -- only the label character changes (`1:` becomes `2:` becomes `3:` becomes `4:`). Each read captures a digit and a newline; the newline is never referenced again.

**Phase 2: Translation.** The four ASCII digit bytes are loaded into four dedicated CPU registers and converted to integers by subtracting the ASCII base offset (`0x30`). From this point until output, all data lives exclusively in registers -- zero memory access during the sort.

**Phase 3: Sort.** The algorithm is a **sorting network** -- a fixed sequence of compare-and-swap (CAS) operations that is mathematically proven to sort any permutation of 4 elements. The network has 3 stages:

```
Stage 1:  CAS(0,1)  CAS(2,3)    -- sort adjacent pairs
Stage 2:  CAS(0,2)  CAS(1,3)    -- cross-compare extremes
Stage 3:  CAS(1,2)              -- resolve the middle pair
```

Five total comparisons. This is provably optimal -- no algorithm can sort 4 elements in fewer comparisons. Each CAS is implemented using **conditional move** (`CMOV`) instructions rather than conditional jumps. This means the sort contains **zero branches**. The CPU never needs to predict which path to take because there is only one path. Every instruction executes unconditionally; the `CMOV` simply decides whether to commit the result or discard it.

**Phase 4: Output.** The four sorted register values are converted back to ASCII, interleaved with space characters into an 8-byte output buffer on the stack, and flushed to stdout in a single write syscall.

### Data Flow Diagram

```
stdin --> stack[8,10,12,14] --> r8,r9,r10,r11 --> sorting network --> r8,r9,r10,r11 --> stack[16..23] --> stdout
              (ASCII)           (integer)          (5x CMOV-CAS)       (sorted)          (ASCII)
```

---

# Level 1 -- The Microscope

## Act I: Carving the Workspace

The program opens with `sub rsp, 32` -- 4 bytes of machine code that claim 32 bytes of stack memory. This is the program's entire world. No heap. No globals. No `.data` section. Thirty-two bytes, subdivided by the architect into three invisible regions: a 4-byte prompt scratchpad at the base, four 2-byte input slots in the middle, and an 8-byte output buffer at the top.

The gaps between regions (bytes 4-7, byte 15) are intentional waste. The architect aligned each buffer to an even offset. This isn't about performance on modern hardware -- it's about clarity of addressing. Every offset in the binary is a clean number.

## Act II: The Four Conversations

The program talks to the human four times, and it's stingy about how.

The prompt `1: ` is 3 bytes: `0x31 0x3A 0x20`. Rather than storing four separate prompts, the architect writes a single 32-bit immediate value to `[rsp]` using `mov dword [rsp], 0x00203a31`. This one instruction stores all 3 characters plus a NUL terminator in a single 4-byte write. The next prompt is created by writing `0x00203a32` to the same address -- only the first byte changes from `0x31` (`'1'`) to `0x32` (`'2'`). The old prompt is destroyed. It's not stored anywhere. It existed for exactly as long as it took the kernel to copy it to the terminal.

The syscall pairs follow the same pattern as the calculator. Write uses explicit `mov` instructions to set register values. Read uses `xor reg, reg` -- the zero-clearing trick. XOR is 2 bytes; `mov reg, 0` is 5 bytes. The architect saves 6 bytes across the four read cycles just from this one idiom.

Each read deposits 2 bytes: the ASCII digit and a newline (`0x0A`). The newline is never touched. It sits in the stack slot, inert, taking up a byte of memory that the program will never look at again.

## Act III: The Great Lift

After all four reads, the program executes the most critical transition: it lifts data out of memory and into registers.

```
movzx r8d,  byte [rsp+8]     ; digit 1 -> r8
movzx r9d,  byte [rsp+10]    ; digit 2 -> r9
movzx r10d, byte [rsp+12]    ; digit 3 -> r10
movzx r11d, byte [rsp+14]    ; digit 4 -> r11
```

`MOVZX` (move with zero-extension) loads a single byte and pads it with zeroes to fill the 32-bit register. This matters: if the architect had used a plain `mov`, the upper bits of the register could contain garbage from previous operations. Zero-extension guarantees the register holds only the value that was loaded. Clean state.

The `sub rNb, 0x30` that follows each load strips the ASCII encoding. The digit `'7'` (`0x37`) becomes the integer `7`. Four subtractions, and the program has crossed from the text world into the math world.

From this point forward, **the stack is irrelevant to the sort**. All four values live in registers `r8d` through `r11d`. Register access is the fastest operation a CPU can perform -- roughly 100x faster than memory access on a cache miss. The architect has loaded the values into the CPU's fastest storage and will keep them there for the entire sort.

## Act IV: The Sorting Network

This is where the binary reveals its most significant shortcut -- one that is genuinely invisible in high-level languages.

### What a Sorting Network Is

A sorting network is a fixed, predetermined sequence of comparisons. Unlike algorithms like quicksort or mergesort, which adapt their comparison pattern based on the data, a sorting network always makes the same comparisons in the same order regardless of input. This sounds wasteful, but for small fixed-size inputs, it's optimal.

For 4 elements, the minimal network requires exactly 5 compare-and-swap operations. No fewer will work. This was proven by mathematical analysis of sorting bounds.

### The CMOV Trick (The Hidden Shortcut)

Here's where it gets interesting. A normal sort in any high-level language -- Python, C, Java -- uses **conditional branches** to swap elements:

```
if a > b:
    a, b = b, a    # this is a branch
```

The CPU must *predict* whether to take that branch before it knows the answer. If it guesses wrong (branch misprediction), it throws away ~15-20 cycles of speculative work and starts over. For a sort with many comparisons, mispredictions pile up.

This binary doesn't branch. Not once. The sort uses `CMOV` -- conditional move:

```
mov eax, r8d        ; save r8d in eax (3 bytes)
cmp r8d, r9d        ; compute r8d - r9d, set flags (3 bytes)
cmovg r8d, r9d      ; if r8d > r9d: r8d = r9d (4 bytes)
cmovg r9d, eax      ; if r8d > r9d: r9d = saved value (4 bytes)
```

Both `CMOV` instructions read the **same flags** from the single `CMP`. This works because `CMOV` does not modify the flags register -- it only conditionally moves data. The CPU doesn't need to predict anything. It evaluates the condition, and either commits the move or treats it as a no-op. Both paths cost the same number of cycles. There is no penalty for the "wrong" outcome because there is no wrong outcome.

This is a 14-byte branchless swap. In a high-level language, you'd write `if a > b: swap(a,b)` and the compiler *might* optimize it to CMOV -- or might not. The architect guarantees it.

### The Network Topology

The 5 CAS operations are arranged in 3 logical stages:

```
Input:   r8   r9   r10   r11

Stage 1: CAS(r8,r9)   CAS(r10,r11)     -- sort the two pairs
Stage 2: CAS(r8,r10)  CAS(r9,r11)      -- push min to r8, max to r11
Stage 3: CAS(r9,r10)                    -- resolve the middle two

Output:  r8 <= r9 <= r10 <= r11
```

Stages 1 and 2 each contain two independent CAS operations. On a superscalar CPU, these can execute in parallel because they touch different registers. The architect has implicitly exposed instruction-level parallelism without writing a single thread or async call.

After the network, the four registers contain the sorted values. Zero memory was accessed. Zero branches were taken. The sort happened entirely inside the register file.

## Act V: The Descent

The program must now reverse the ASCII conversion and build a human-readable output string.

`add rNb, 0x30` converts each integer back to its ASCII representation. The sorted integer `2` becomes `0x32` (`'2'`). Four additions, and we're back in the text world.

The output buffer at `[rsp+16]` is built by interleaving the digit bytes with `0x20` (space) and terminating with `0x0A` (newline):

```
[rsp+16] = r8b      ; first digit
[rsp+17] = 0x20     ; space
[rsp+18] = r9b      ; second digit
[rsp+19] = 0x20     ; space
[rsp+20] = r10b     ; third digit
[rsp+21] = 0x20     ; space
[rsp+22] = r11b     ; fourth digit
[rsp+23] = 0x0a     ; newline
```

Eight bytes. One write syscall. Done.

## Act VI: The Exit

`mov eax, 60` / `xor edi, edi` / `syscall`. The kernel reclaims everything. The 32-byte stack frame, the sorted registers, the output buffer -- all gone.

---

## The Shortcuts, Summarized

| Technique | What It Avoids | Why It Matters |
|---|---|---|
| **Sorting network** | Loop-based sorts, recursion | Fixed 5 comparisons, provably optimal for n=4 |
| **CMOV (conditional move)** | Conditional jumps (jcc) | Zero branch mispredictions, constant-time swap |
| **Register-only sort** | Memory loads/stores during sort | ~100x faster than cache-miss memory access |
| **Prompt mutation** | 4 separate string allocations | 3 bytes saved per prompt, one memory region |
| **XOR zeroing** | `mov reg, 0` (5 bytes) | 2 bytes per use, CPU recognizes the idiom |
| **MOVZX** | Manual masking / garbage upper bits | Clean 32-bit register state in one instruction |
| **Implicit parallelism** | Thread management, async code | Superscalar CPU can run independent CAS pairs simultaneously |

## The Numbers

| Metric | Value |
|---|---|
| Total binary size | 493 bytes |
| ELF + program headers | 120 bytes |
| Executable logic | 373 bytes |
| Sorting network size | 70 bytes (5 CAS x 14 bytes) |
| Branches in sort | 0 |
| Comparisons | 5 (optimal) |
| Syscalls | 3 types (read, write, exit) |
| Memory access during sort | 0 |
| Registers used for sort | 4 (r8d-r11d) + 1 temp (eax) |
