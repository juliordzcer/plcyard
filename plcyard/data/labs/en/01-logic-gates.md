---
title: Logic gates with contacts
simulation: io
level: 1
symbols:
- %I0.0 Input A
- %I0.1 Input B
- %I0.2 Input C
- %I0.3 Input D
- %I0.4 Input E
- %I0.5 Input F
- %I0.6 Input G
- %Q0.0 AND output
- %Q0.1 OR output
- %Q0.2 NOT output
- %Q0.3 XOR output
---
# 1. Logic gates with contacts

**Goal:** build AND, OR, NOT and XOR with `XIC`/`XIO` contacts in series and in parallel.

## Inputs and outputs

| Address | Use |
| --- | --- |
| %I0.0, %I0.1 | AND gate inputs |
| %I0.2, %I0.3 | OR gate inputs |
| %I0.4 | inverter input |
| %I0.5, %I0.6 | XOR inputs |
| %Q0.0 … %Q0.3 | AND, OR, NOT, XOR |

## Requirements

1. %Q0.0 turns on only when %I0.0 **and** %I0.1 are closed.
2. %Q0.1 turns on when %I0.2 **or** %I0.3 is closed.
3. %Q0.2 turns on when %I0.4 is **open**.
4. %Q0.3 turns on when %I0.5 and %I0.6 are **different**.

## Hints

- Contacts in series = AND; parallel branches = OR; `XIO` = NOT.
- XOR needs two branches: (A and not B) or (not A and B).

## How to test it

Download, put the PLC in RUN and walk through each gate's truth table with the switches.
