---
title: Logic gates with contacts
simulation: io
level: 1
symbols:
- I:1/0 Input A
- I:1/1 Input B
- I:1/2 Input C
- I:1/3 Input D
- I:1/4 Input E
- I:1/5 Input F
- I:1/6 Input G
- O:2/0 AND output
- O:2/1 OR output
- O:2/2 NOT output
- O:2/3 XOR output
---
# 1. Logic gates with contacts

**Goal:** build AND, OR, NOT and XOR with XIC/XIO contacts in series and in parallel.

## Inputs and outputs

| Address | Use |
| --- | --- |
| I:1/0, I:1/1 | AND gate inputs |
| I:1/2, I:1/3 | OR gate inputs |
| I:1/4 | inverter input |
| I:1/5, I:1/6 | XOR inputs |
| O:2/0 … O:2/3 | AND, OR, NOT, XOR |

## Requirements

1. O:2/0 turns on only when I:1/0 **and** I:1/1 are closed.
2. O:2/1 turns on when I:1/2 **or** I:1/3 is closed.
3. O:2/2 turns on when I:1/4 is **open**.
4. O:2/3 turns on when I:1/5 and I:1/6 are **different**.

## Hints

- Contacts in series = AND; parallel branches = OR; XIO = NOT.
- XOR needs two branches: (A and not B) or (not A and B).

## How to test it

Download, put the PLC in RUN and walk through each gate's truth table with the switches.
