# The Logic Narrative

> Upward-compiled from `calc_bin` -- a 300-byte Linux x86_64 ELF executable.
> Final stage of the Human Compiler Pipeline.

---

## Act I: The Stage

The program's first move is to carve out a workspace. It pushes the stack pointer down by 32 bytes -- claiming a small slab of fast memory that will serve as the program's entire universe. No heap allocations, no global data section, no luxury. Just 32 bytes on the stack. Everything that happens in this program happens within that window.

The slab has an implicit layout that the architect decided at design time. Bytes 0 through 3 are a reusable scratchpad for prompt text. Bytes 8 and 9 hold the first digit. Bytes 10 and 11 hold the second. Bytes 12 through 14 are reserved for the final answer. Gaps exist between these regions (bytes 4-7, for example) -- wasted space, intentionally, because the CPU accesses memory fastest when data falls on natural alignment boundaries.

---

## Act II: The Conversation

The program needs two numbers from the human. Rather than storing two separate prompt strings, the architect played a trick: it writes the bytes for `A: ` directly into the scratchpad at position zero, sends those 3 bytes out through the write syscall to the terminal, then *overwrites those same bytes* with `B: ` for the second prompt. One memory location, two messages. The prompt is ephemeral -- it exists only long enough to be pushed out the door to the display.

Between each prompt, the program drops into a read syscall and waits. The kernel suspends execution entirely. The CPU does nothing. When the human presses a key and hits enter, the kernel deposits two bytes into the stack -- the ASCII digit and a trailing newline character. The program never looks at the newline. It's dead weight that rides in on the read and is silently ignored.

There's an interesting asymmetry in how the registers are prepared for read vs. write. For write, the program uses full `mov` instructions to load the syscall number and file descriptor. For read, it uses `xor reg, reg` -- a register XORed with itself is always zero. This is a well-known x86 idiom. It's shorter (2 bytes instead of 5) and faster (the CPU recognizes this pattern and doesn't even bother reading the register's old value). The architect uses this shortcut because both the syscall number for read and the file descriptor for stdin happen to be zero.

---

## Act III: The Translation Problem

Here's the core tension of the program: humans think in text, CPUs think in numbers, and this program has to cross that boundary twice.

The digits arrive as ASCII -- the character `'3'` is actually the byte value `0x33`, and `'7'` is `0x77`. The ASCII table was designed with a gift for programmers: the digit characters are arranged contiguously starting at `0x30`. So converting ASCII to a real number is a single subtraction. Subtract `0x30` from any ASCII digit and you get its numeric value. The program does this with `sub al, 0x30` -- a one-byte instruction operating on just the lowest 8 bits of the accumulator. No function call, no lookup table. One subtraction, and the text world becomes the math world.

The addition itself is almost anticlimactic. One `add` instruction. Two registers collide, their values merge, and the sum appears in `eax`. The entire reason this program exists -- the actual computation -- takes exactly two bytes of machine code.

---

## Act IV: The Fork in the Road

Now the program faces its only real decision. The sum of two single-digit numbers can be anywhere from 0 to 18. If it's below 10, the result is one character. If it's 10 or above, it's two characters. The program must figure out which case it's in, because the output buffer and the byte count for the write syscall depend on it.

It compares the sum against 10. If the sum is less, the program jumps forward, skipping the two-digit logic entirely. If not, it falls through into the two-digit path. This is another micro-optimization: the architect arranged the code so that the "harder" case (two digits) is the fall-through path, and the "easy" case requires the jump. In branch prediction terms, this doesn't matter much for a program that runs once -- but it reveals a habit of thinking: put the heavier logic on the natural path and let the lighter logic leap over it.

The two-digit path exploits a mathematical constraint. Since the maximum sum is 18, the tens digit can only ever be `1`. So the program doesn't compute it. It hard-codes the ASCII byte `0x31` (the character `'1'`) directly into the output buffer. Then it subtracts 10 from the sum, adds `0x30` to convert the remainder back to ASCII, and drops that into the next byte. The program never divides. It never uses modulo. It avoids the most expensive arithmetic operations the CPU offers by recognizing that the problem domain is small enough to cheat.

The single-digit path is simpler. Add `0x30` to the sum, store one byte, done.

Both paths append `0x0A` -- the newline character -- at the end of the output buffer. Both paths set `rdx` to the correct byte count (2 or 3). And both paths converge at the same write syscall.

---

## Act V: The Exit

The program sends the output buffer to stdout through one final syscall, then loads `60` into `eax` -- the number for `sys_exit` -- zeros out `edi` to signal success, and fires the syscall one last time. The kernel reclaims the process. The 32-byte stack frame evaporates. Nothing persists.

---

## The Shortcuts, Summarized

| Technique | What it avoids | Savings |
|---|---|---|
| **Prompt reuse** | A second string in memory | 4 bytes of data |
| **XOR zeroing** (`xor reg, reg`) | `mov reg, 0` | 3 bytes per use, faster on silicon |
| **ASCII arithmetic** (`sub 0x30` / `add 0x30`) | Lookup tables, function calls | Entire conversion in 1 instruction |
| **Hardcoded tens digit** | Division and modulo operations | Avoids the CPU's slowest math |
| **Stack-only architecture** | `.data`, `.bss`, relocations, dynamic linking | Zero external dependencies |

---

## The Numbers

| Metric | Value |
|---|---|
| Total binary size | 300 bytes |
| ELF + program headers | 120 bytes |
| Executable logic | 180 bytes |
| Syscalls used | 3 (`read`, `write`, `exit`) |
| External dependencies | 0 |
| Stack frame size | 32 bytes |
| Bytes dedicated to the actual addition | 2 |

The whole thing is 180 bytes of logic. It asks, listens, thinks for one clock cycle, translates back into the human's language, and disappears.
