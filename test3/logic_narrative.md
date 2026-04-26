# Human Compiler -- Multi-Resolution Analysis: Prime Generator

> Source of Truth: `primes_bin` (300 bytes, Linux x86_64 ELF)

---

# Level 10 -- The Label

A 300-byte program that prints all 25 prime numbers up to 100, using no division, no loops over candidates, and no standard sieve -- just two preloaded 64-bit bitmasks and a hardware bit-scanner.

---

# Level 5 -- The Discovery

Three techniques in this binary that standard textbooks don't teach:

### 1. A 64-Bit Register Is a 64-Element Boolean Array

The binary encodes "is N prime?" for 64 numbers in a single register. Bit 2 is set because 2 is prime. Bit 4 is clear because 4 isn't. The entire sieve result for numbers 0-63 fits in one 64-bit value: `0x28208A20A08A28AC`. A second register covers 64-100.

**What humans can learn**: Any boolean property over a bounded integer domain can be packed into registers. A single `AND` operation then performs 64 simultaneous lookups. This is the foundation of bitboard chess engines, bloom filters, and compiler register allocators -- but it's rarely presented as a *sieve* technique.

### 2. BSF Is a Free Search

`BSF` (Bit Scan Forward) finds the lowest set bit in a 64-bit register in one clock cycle. The CPU implements this as a hardware priority encoder -- a physical circuit that resolves 64 inputs simultaneously, not a loop. There is no Python, C, or Java equivalent that compiles to a single instruction. `BSF` + `BTR` (Bit Test and Reset) together let you enumerate all set bits in ascending order without maintaining a counter, without a comparison, and without knowing how many bits are set.

**What humans can learn**: When your problem is "find the next element in a sparse set," bit-scanning is O(1) per element regardless of the set's density. Languages are starting to expose this (`Integer.numberOfTrailingZeros` in Java, `__builtin_ctz` in GCC), but most developers don't know it maps to a single hardware instruction.

### 3. Division Is Multiplication in Disguise

The binary never executes a `DIV` instruction. To convert a prime number to decimal digits (dividing by 10), it multiplies by the magic constant `0xCCCCCCCD` and shifts right by 35 bits. This works because:

```
0xCCCCCCCD / 2^35 = 0.10000000000582...  ≈  1/10
```

So `n * 0xCCCCCCCD >> 35 = floor(n/10)` for all n < 1000. The binary splits this across two instructions: `MUL` gives a 64-bit result in `edx:eax`, and `SHR edx, 3` extracts the quotient from the upper 32 bits (effectively >> 35 total).

**What humans can learn**: Compilers do this automatically for division by constants, but most developers don't know *why* their compiled code has mysterious multiply instructions where they wrote division. The binary makes the trick explicit: multiplication is 3 cycles, division is 30+ cycles. The tradeoff is knowing the divisor at compile time.

---

# Level 1 -- The Microscope

## Act I: The Architect's Sieve

Before the program ever runs, the architect performed a sieve using bit-parallel operations on paper:

**Step 1**: Start with all odd numbers 3-63 plus 2, encoded as a bitmask:
```
init = 0xAAAAAAAAAAAAAAACi
       (bit 2 set, all odd bits 3-63 set, bit 1 cleared)
```

**Step 2**: Compute composite masks -- every odd multiple of each small prime:
```
mult_of_3 = 0x8208208208208200   (bits 9,15,21,27,33,39,45,51,57,63)
mult_of_5 = 0x0080000802000000   (bits 25,35,55)
mult_of_7 = 0x8002000800200000   (bits 21,35,49,63)
```

**Step 3**: Clear composites using ANDN (AND with NOT of mask):
```
result = init & ~mult_of_3 & ~mult_of_5 & ~mult_of_7
       = 0x28208A20A08A28AC
```

Each ANDN would be 2 instructions at runtime (`NOT` + `AND`), clearing an entire prime's composite family across 64 numbers in one clock cycle. But the architect went further: since all inputs are constants, the entire sieve collapses to a single `MOV` instruction that loads the pre-computed result. The sieve happened at *design time*. The runtime cost is zero.

This is the deepest alien insight: **the sieve is a compile-time computation baked into the machine code as a constant**. The traditional sieve runs at O(n log log n). This one runs at O(1) -- it's a lookup of a precomputed answer encoded in the instruction stream itself.

The same process produced `0x0000000202088288` for primes 67-97.

## Act II: The Priority Encoder

With the sieve result loaded in `r8`, the program enters an extraction loop:

```
.loop_r8:
    bsf rcx, r8       ; rcx = index of lowest set bit
    jz  .done          ; if r8 == 0, no more primes
    btr r8, rcx        ; clear that bit
    mov r12d, ecx      ; save prime number
    call .print_num    ; print it
    jmp .loop_r8       ; repeat
```

**BSF** (Bit Scan Forward) is the key instruction. It takes a 64-bit register and returns the position of the lowest set bit. Inside the CPU, this is a **priority encoder** -- a combinational logic circuit where 64 input lines feed into a tree of OR gates and multiplexers that resolve the answer in constant time. No iteration. No comparison chain. The hardware tests all 64 bits simultaneously.

For `r8 = 0x28208A20A08A28AC`:
- First BSF returns 2 (bit 2 = prime 2)
- BTR clears bit 2, r8 becomes `0x28208A20A08A28A8`
- Next BSF returns 3 (bit 3 = prime 3)
- BTR clears bit 3, r8 becomes `0x28208A20A08A28A0`
- ...continues until r8 = 0 (all primes extracted)

The primes emerge in ascending order because BSF always finds the *lowest* set bit. No sorting needed. The bit positions *are* the sorted sequence.

After exhausting `r8`, the program switches to `r9` with one extra step: `lea r12d, [ecx+64]` adds 64 to the bit position, recovering the actual prime number (bit 3 of r9 = prime 67).

## Act III: The Magic Multiplier

Each extracted prime must be printed as decimal ASCII. The number is in `r12d` (range 2-97). The binary needs the tens digit (`n/10`) and ones digit (`n%10`).

A normal programmer would write `div`. The binary doesn't. Here's what it does:

```
0x00C6: mov eax, r12d             ; eax = prime number
0x00C9: mov ecx, 0xCCCCCCCD       ; load magic constant
0x00CE: mul ecx                    ; edx:eax = n * 0xCCCCCCCD
0x00D0: shr edx, 3                ; edx = n / 10
0x00D3: imul eax, edx, 10         ; eax = (n/10) * 10
0x00D6: mov ecx, r12d             ; ecx = n
0x00D9: sub ecx, eax              ; ecx = n % 10
```

The magic number `0xCCCCCCCD` is the modular multiplicative inverse of 10 in fixed-point arithmetic. When you multiply an integer by this constant, the upper 32 bits of the 64-bit result contain `n * (2^32 * 4/10)`. Shifting right by 3 more bits (total shift: 35) yields `floor(n/10)`.

The remainder is computed without division too: `n - (n/10)*10`. The `IMUL eax, edx, 10` instruction multiplies the quotient by 10, and `SUB` gives the remainder.

Total cost: 2 multiplies + 1 shift + 1 subtract = ~6 cycles.
A `DIV` instruction: ~30 cycles, and it stalls the pipeline.

After the digits are computed, the binary adds `0x30` to convert to ASCII (same trick as the calculator), builds a 2-3 byte string on the stack, and fires a `write` syscall.

## Act IV: The Branching Structure

The entire binary has exactly **4 conditional jumps**:

| Jump | Purpose | Type |
|---|---|---|
| `jz` at 0x94 | r8 exhausted? | Loop exit |
| `jz` at 0xA8 | r9 exhausted? | Loop exit |
| `jz` at 0xDD | Single digit? | Output format |
| `jmp` at 0xA2/0xB7 | Loop back | Unconditional |

There are no branches in the sieve (it's precomputed), no branches in the extraction logic (BSF is branchless), and no branches in the division (magic multiply is branchless). The only decisions the program makes are "are there more primes?" and "is this number one or two digits?"

---

## The Shortcuts, Summarized

| Technique | Replaces | Speedup Factor |
|---|---|---|
| **Bit-packed sieve in registers** | Array of booleans in memory | 64x density, 0 memory access |
| **Compile-time sieve collapse** | Runtime O(n log log n) sieve | Infinite (O(1) at runtime) |
| **BSF (hardware bit scan)** | Linear search for next prime | O(1) vs O(n) per extraction |
| **BTR (atomic bit clear)** | Read + mask + write | 1 instruction vs 3 |
| **Magic-number multiply** | DIV instruction | ~10x faster (3 vs 30 cycles) |
| **LEA for addition** | ADD + MOV | 1 instruction vs 2 |

## The Numbers

| Metric | Value |
|---|---|
| Total binary size | 300 bytes |
| ELF + program headers | 120 bytes |
| Executable logic | 180 bytes |
| Primes found | 25 |
| DIV instructions | 0 |
| Runtime sieve operations | 0 (precomputed) |
| Bits encoding the sieve | 128 (two 64-bit registers) |
| BSF extractions | 25 (one per prime) |
