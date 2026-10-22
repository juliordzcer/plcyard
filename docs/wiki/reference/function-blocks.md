# Function blocks (FBD)

Blocks of the function block diagram editor. An input pin takes a wire or an operand (a tag,
an address or a constant); an output pin may feed wires and write an operand. Blocks with an
instance keep their state in a tag of that type.

## Bit logic

| Block | What it does | Inputs | Outputs | Instance |
| --- | --- | --- | --- | --- |
| `AND` | AND (more inputs: right-click → Add input) | IN1 (BOOL), IN2 (BOOL) | OUT (BOOL) | — |
| `OR` | OR (more inputs: right-click → Add input) | IN1 (BOOL), IN2 (BOOL) | OUT (BOOL) | — |
| `XOR` | Exclusive OR | IN1 (BOOL), IN2 (BOOL) | OUT (BOOL) | — |
| `NOT` | NOT | IN (BOOL) | OUT (BOOL) | — |
| `SR` | Set dominant flip-flop | S1 (BOOL), R (BOOL) | Q1 (BOOL) | — |
| `RS` | Reset dominant flip-flop | S (BOOL), R1 (BOOL) | Q1 (BOOL) | — |
| `R_TRIG` | Rising edge | CLK (BOOL) | Q (BOOL) | — |
| `F_TRIG` | Falling edge | CLK (BOOL) | Q (BOOL) | — |

## Timers

| Block | What it does | Inputs | Outputs | Instance |
| --- | --- | --- | --- | --- |
| `TON` | On delay | IN (BOOL), PT (number) | Q (BOOL), ET (number) | TIMER |
| `TOF` | Off delay | IN (BOOL), PT (number) | Q (BOOL), ET (number) | TIMER |
| `TP` | Pulse | IN (BOOL), PT (number) | Q (BOOL), ET (number) | TIMER |
| `RTO` | Retentive on delay | IN (BOOL), PT (number), R (BOOL) | Q (BOOL), ET (number) | TIMER |

## Counters

| Block | What it does | Inputs | Outputs | Instance |
| --- | --- | --- | --- | --- |
| `CTU` | Count up | CU (BOOL), R (BOOL), PV (number) | Q (BOOL), CV (number) | COUNTER |
| `CTD` | Count down | CD (BOOL), LD (BOOL), PV (number) | Q (BOOL), CV (number) | COUNTER |

## Compare

| Block | What it does | Inputs | Outputs | Instance |
| --- | --- | --- | --- | --- |
| `EQ` | Equal | IN1 (number), IN2 (number) | OUT (BOOL) | — |
| `NE` | Not equal | IN1 (number), IN2 (number) | OUT (BOOL) | — |
| `LT` | Less than | IN1 (number), IN2 (number) | OUT (BOOL) | — |
| `LE` | Less or equal | IN1 (number), IN2 (number) | OUT (BOOL) | — |
| `GT` | Greater than | IN1 (number), IN2 (number) | OUT (BOOL) | — |
| `GE` | Greater or equal | IN1 (number), IN2 (number) | OUT (BOOL) | — |
| `LIMIT` | Limit to a range | MN (number), IN (number), MX (number) | OUT (number) | — |

## Math

| Block | What it does | Inputs | Outputs | Instance |
| --- | --- | --- | --- | --- |
| `ADD` | Add (more inputs: right-click → Add input) | IN1 (number), IN2 (number) | OUT (number) | — |
| `SUB` | Subtract | IN1 (number), IN2 (number) | OUT (number) | — |
| `MUL` | Multiply (more inputs: right-click → Add input) | IN1 (number), IN2 (number) | OUT (number) | — |
| `DIV` | Divide | IN1 (number), IN2 (number) | OUT (number) | — |
| `MOD` | Modulo | IN1 (number), IN2 (number) | OUT (number) | — |
| `MAX` | Maximum (more inputs: right-click → Add input) | IN1 (number), IN2 (number) | OUT (number) | — |
| `MIN` | Minimum (more inputs: right-click → Add input) | IN1 (number), IN2 (number) | OUT (number) | — |
| `ABS` | Absolute value | IN (number) | OUT (number) | — |
| `SQRT` | Square root | IN (number) | OUT (number) | — |

## Move

| Block | What it does | Inputs | Outputs | Instance |
| --- | --- | --- | --- | --- |
| `MOVE` | Move | IN (number) | OUT (number) | — |
| `SEL` | Select | G (BOOL), IN0 (number), IN1 (number) | OUT (number) | — |
| `TO_BCD` | Integer to BCD | IN (number) | OUT (number) | — |
| `FROM_BCD` | BCD to integer | IN (number) | OUT (number) | — |
| `SCALE` | Scale a range | IN (number), IN_MIN (number), IN_MAX (number), OUT_MIN (number), OUT_MAX (number) | OUT (number) | — |

## Process

| Block | What it does | Inputs | Outputs | Instance |
| --- | --- | --- | --- | --- |
| `PID` | PID controller | PV (number), SP (number) | CV (number) | PID |
