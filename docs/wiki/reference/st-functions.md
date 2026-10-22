# Structured text functions

Functions callable in expressions, with their number of arguments. Conversions `X_TO_Y` work
between BOOL, SINT, INT, DINT, LINT, REAL, LREAL, TIME, WORD, DWORD and BYTE.

| Function | Arguments |
| --- | --- |
| `ABS` | 1 |
| `BCD_TO_INT` | 1 |
| `COS` | 1 |
| `EXP` | 1 |
| `INT_TO_BCD` | 1 |
| `LIMIT` | 3 |
| `LN` | 1 |
| `MAX` | 2 |
| `MIN` | 2 |
| `ROUND` | 1 |
| `SEL` | 3 |
| `SIN` | 1 |
| `SQRT` | 1 |
| `TAN` | 1 |
| `TRUNC` | 1 |

Blocks called on their tag: `Tag.TON(IN := …, PT := …)`, `TOF`, `TP`, `RTO`, `CTU`
(`CU`, `R`, `PV`), `CTD` (`CD`, `LD`, `PV`), `PID` (`PV`, `SP`, `CV =>`). Routines and blocks:
`JSR(Name);`, `"Function"(In := x, Out => y);`, `"Instance"(…);`.
