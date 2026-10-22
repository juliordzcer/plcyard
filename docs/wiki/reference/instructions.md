# Instructions

Every ladder instruction, generated from the instruction set. The *IEC* column is the name
shown in the IEC-symbols notation (Tools → Options). Operands in *italics* are optional.

## Bit

| Mnemonic | IEC | What it does | Operands |
| --- | --- | --- | --- |
| `XIC` | `NO` | Examine if closed (normally open contact) | Bit (bool) |
| `XIO` | `NC` | Examine if open (normally closed contact) | Bit (bool) |
| `OTE` | `COIL` | Output energize (coil) | Bit (bool) |
| `OTL` | `S` | Output latch (set coil) | Bit (bool) |
| `OTU` | `R` | Output unlatch (reset coil) | Bit (bool) |
| `ONS` | `P_TRIG` | One shot (rising edge of the rung) | Storage bit (bool) |
| `OSR` | `OSR` | One shot rising | Storage bit (bool)<br>Output bit (bool) |
| `OSF` | `OSF` | One shot falling | Storage bit (bool)<br>Output bit (bool) |
| `P` | `P` | Positive edge of an operand | Operand (bool)<br>Edge memory bit (bool) |
| `N` | `N` | Negative edge of an operand | Operand (bool)<br>Edge memory bit (bool) |

## Timer/Counter

| Mnemonic | IEC | What it does | Operands |
| --- | --- | --- | --- |
| `TON` | `TON` | Timer on delay | Timer (timer)<br>Preset (time)<br>*Accum (value)* |
| `TOF` | `TOF` | Timer off delay | Timer (timer)<br>Preset (time)<br>*Accum (value)* |
| `RTO` | `RTO` | Retentive timer on | Timer (timer)<br>Preset (time)<br>*Accum (value)* |
| `TP` | `TP` | Pulse timer | Timer (timer)<br>Preset (time)<br>*Accum (value)* |
| `CTU` | `CTU` | Count up | Counter (counter)<br>Preset (value)<br>*Reset (bool)* |
| `CTD` | `CTD` | Count down | Counter (counter)<br>Preset (value)<br>*Load (bool)* |
| `RES` | `RESET` | Reset a timer, counter or control | Timer or counter (element) |

## Compare

| Mnemonic | IEC | What it does | Operands |
| --- | --- | --- | --- |
| `EQU` | `CMP ==` | Equal | Source A (value)<br>Source B (value) |
| `NEQ` | `CMP <>` | Not equal | Source A (value)<br>Source B (value) |
| `LES` | `CMP <` | Less than | Source A (value)<br>Source B (value) |
| `LEQ` | `CMP <=` | Less than or equal | Source A (value)<br>Source B (value) |
| `GRT` | `CMP >` | Greater than | Source A (value)<br>Source B (value) |
| `GEQ` | `CMP >=` | Greater than or equal | Source A (value)<br>Source B (value) |
| `LIM` | `IN_RANGE` | Limit test (value within range) | Low limit (value)<br>Test (value)<br>High limit (value) |
| `MEQ` | `MEQ` | Masked equal | Source (value)<br>Mask (value)<br>Compare (value) |

## Math

| Mnemonic | IEC | What it does | Operands |
| --- | --- | --- | --- |
| `ADD` | `ADD` | Add | Source A (value)<br>Source B (value)<br>Dest (dest) |
| `SUB` | `SUB` | Subtract | Source A (value)<br>Source B (value)<br>Dest (dest) |
| `MUL` | `MUL` | Multiply | Source A (value)<br>Source B (value)<br>Dest (dest) |
| `DIV` | `DIV` | Divide | Source A (value)<br>Source B (value)<br>Dest (dest) |
| `MOD` | `MOD` | Modulo | Source A (value)<br>Source B (value)<br>Dest (dest) |
| `NEG` | `NEG` | Negate | Source (value)<br>Dest (dest) |
| `SQR` | `SQRT` | Square root | Source (value)<br>Dest (dest) |
| `SCP` | `SCP` | Scale with parameters | Input (value)<br>Input min (value)<br>Input max (value)<br>Scaled min (value)<br>Scaled max (value)<br>Output (dest) |
| `NORM_X` | `NORM_X` | Normalize to 0.0-1.0 | Min (value)<br>Value (value)<br>Max (value)<br>Out (dest) |
| `SCALE_X` | `SCALE_X` | Scale 0.0-1.0 to a range | Min (value)<br>Value (value)<br>Max (value)<br>Out (dest) |

## Move/Logical

| Mnemonic | IEC | What it does | Operands |
| --- | --- | --- | --- |
| `MOV` | `MOVE` | Move | Source (value)<br>Dest (dest) |
| `NOT` | `NOT` | Bitwise NOT | Source (value)<br>Dest (dest) |
| `TOD` | `TO_BCD` | Convert to BCD | Source (value)<br>Dest (dest) |
| `FRD` | `FROM_BCD` | Convert from BCD | Source (value)<br>Dest (dest) |
| `AND` | `AND` | Bitwise AND | Source A (value)<br>Source B (value)<br>Dest (dest) |
| `OR` | `OR` | Bitwise OR | Source A (value)<br>Source B (value)<br>Dest (dest) |
| `XOR` | `XOR` | Bitwise XOR | Source A (value)<br>Source B (value)<br>Dest (dest) |
| `MVM` | `MVM` | Masked move | Source (value)<br>Mask (value)<br>Dest (dest) |
| `CLR` | `CLR` | Clear | Dest (dest) |

## Array

| Mnemonic | IEC | What it does | Operands |
| --- | --- | --- | --- |
| `BSL` | `BSL` | Bit shift left | Array (array)<br>Control (control)<br>Source bit (bool)<br>Length (value) |
| `BSR` | `BSR` | Bit shift right | Array (array)<br>Control (control)<br>Source bit (bool)<br>Length (value) |
| `SQO` | `SQO` | Sequencer output | Array (array)<br>Mask (value)<br>Dest (dest)<br>Control (control)<br>Length (value)<br>*Position (value)* |
| `SQC` | `SQC` | Sequencer compare | Array (array)<br>Mask (value)<br>Source (value)<br>Control (control)<br>Length (value)<br>*Position (value)* |
| `SQL` | `SQL` | Sequencer load | Array (array)<br>Source (value)<br>Control (control)<br>Length (value)<br>*Position (value)* |
| `COP` | `COP` | Copy array elements | Source (array)<br>Dest (array)<br>Length (value) |
| `FLL` | `FLL` | Fill array elements | Source (value)<br>Dest (array)<br>Length (value) |

## Program Control

| Mnemonic | IEC | What it does | Operands |
| --- | --- | --- | --- |
| `JSR` | `CALL` | Jump to subroutine (call a routine) | Routine (routine) |
| `RET` | `RET` | Return | — |
| `CALL` | `CALL` | Call a function or function block | Block (block)<br>*up to 8 parameters `Name:=value` or `Name=>tag`* |
| `NOP` | `NOP` | No operation | — |

## Process

| Mnemonic | IEC | What it does | Operands |
| --- | --- | --- | --- |
| `PID` | `PID` | PID controller | PID (pid)<br>Process variable (value)<br>Control variable (dest)<br>*Setpoint (value)*<br>*Tieback (value)*<br>*Master loop (pid)*<br>*Inhold bit (bool)*<br>*Inhold value (value)* |

### PID

Every loop update time (UPD) while the rung is true. The process variable is scaled from
MINI..MAXI to MINS..MAXS (engineering units), the output in % goes to the control variable
scaled to MINCV..MAXCV. Optional: a setpoint (else the SP member), a tieback the output follows
in manual, a master loop whose output (in %) becomes this loop's setpoint (cascade), and an
inhold bit that holds the output at the inhold value (bumpless restart). PID Setup in the
editor sets the members.

### CALL

A function by name, a function block by its instance (`Motor1`, or `#Inner` inside a block).
Parameters: `Start:=Button` (input) or `Running=>Lamp` (output). EN → ENO.
