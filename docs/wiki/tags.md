# Tags, data types and arrays

A **tag** is a named piece of PLC memory. Open the tag list from the project tree (Ctrl+T).

| Type | Holds |
| --- | --- |
| BOOL | TRUE / FALSE |
| SINT, INT, DINT | 8, 16, 32-bit integers |
| REAL | floating point |
| TIME | a duration, `T#2s500ms` |
| TIMER | `.PRE .ACC .DN .EN .TT` (IEC: `.PT .ET .Q .IN`) |
| COUNTER | `.PRE .ACC .DN .CU .CD .OV .UN` (IEC: `.PV .CV .Q`) |
| CONTROL | `.LEN .POS .DN .EN …` for shift and sequencer instructions |
| PID | setpoint, gains, limits, alarms and modes of a PID loop |

Integer math wraps around and sets `Overflow`.

## I/O and marker addresses

You may use addresses directly, or give them a tag name (an alias with a description):
`%I0.0` input bit, `%Q0.0` output bit, `%IW64` analog input word, `%M10.0` marker bit,
`%MW20` marker word.

## Arrays

`DINT[10]` (or `Array[1..5] of INT`), indexed by a constant or a tag: `Values[Step]`. An index out
of range is a major fault.

## Data types

Your own structures: **Project → New data type…**, add members of any type (other data types and arrays
included). `Recipe[2].FillTime` reads a member of an element of an array of a data type.

## Forcing

Right-click an I/O point in the tag list or the ladder to force it ON or OFF. Forced inputs are
applied after the input scan, forced outputs before the output scan, and the FORCE light is on
while any force is set.
