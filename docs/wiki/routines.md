# Routines and blocks

A program can hold many routines, each in LD, ST or FBD, each open in its own tab.

- **Main routine**: runs every scan.
- **Subroutine**: runs when called with `JSR` (ladder) or `JSR(Name);` (ST). Shares the program's
  tags.
- **Function (FC)**: has an interface of **Input**, **Output**, **InOut** and **Temp** variables.
  Call it with a `CALL` box or `"Name"(In := x, Out => y);`.
- **Function block (FB)**: like a function plus **Static** variables that keep their value between
  calls. Each **instance** (a tag of the block's type) has its own copy: one motor-starter block,
  ten motors.

Inside a function or block, `#Name` refers to its own interface variables.

Create one with **Project → Add routine or block…**: choose the kind and the language. Rename or delete it from
the project tree.

Examples: *Traffic lights (routines)* (a ladder main calling an ST sequence), *Silo (function
block)*, *Motor starters (function block)*.
