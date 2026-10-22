# Structured text

```
IF Start AND NOT Stop THEN
    Motor := TRUE;
ELSIF Stop THEN
    Motor := FALSE;
END_IF;

Delay.TON(IN := Motor, PT := T#5s);
Lamp := Delay.DN;
```

- Statements: `:=`, `IF/ELSIF/ELSE`, `CASE`, `FOR`, `WHILE`, `REPEAT`, `EXIT`, `RETURN`.
- Operators: `+ - * / MOD **`, `AND OR XOR NOT`, `= <> < <= > >=`.
- Literals: `TRUE`, `16#FF`, `2#1010`, `T#1m30s`, `3.5`.
- Timers, counters and PID are called on their tag: `Delay.TON(…)`, `Parts.CTU(CU := Sensor, PV := 10)`,
  `Loop.PID(PV := Level, SP := 50.0, CV => Valve)`.
- Routines and blocks: `JSR(Fill);`, `"Scale"(In := Raw, Out => Level);`, `"Motor1"(Run := Start);`.
- Arrays and members: `Recipe[Step].FillTime`.

The editor colours keywords, numbers lines and shows errors as you type. Online, a watch list next to
the code shows the live value of every name used.

See the [function reference](reference/st-functions.md).
