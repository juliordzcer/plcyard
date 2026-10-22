# Notations

PLCYard is one PLC, and you choose how it is written in **Tools → Options → Notation**. The
program is the same in both: switch at any time, and read either style of documentation or
manual.

| | Mnemonics | IEC symbols |
| --- | --- | --- |
| Contacts and coils | `XIC`, `XIO`, `OTE`, `OTL`, `OTU` | NO, NC, coil, S, R |
| Boxes | `MOV`, `EQU`, `LIM`, `JSR` | `MOVE`, `CMP ==`, `IN_RANGE`, `CALL` |
| I/O | `Local:1:I.Data.0`, `Local:2:O.Data.3` | `%I0.0`, `%Q0.3` |
| Analog I/O | `Local:7:I.Ch0Data` | `%IW64` |
| Timer members | `.PRE` `.ACC` `.DN` `.EN` `.TT` | `.PT` `.ET` `.Q` `.IN` |
| Counter members | `.PRE` `.ACC` `.DN` | `.PV` `.CV` `.Q` |
| System bits | `S:FS`, `S:V` | `FirstScan`, `Overflow` |

Both spellings are accepted when you type an operand, whichever notation is shown. Files store the
canonical form (`%I0.0`, `.PRE`), so a project opens the same for everyone.

The full list of mnemonics and their IEC names is in the [instruction reference](reference/instructions.md).
