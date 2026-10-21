# Bugs: plc-sim

Found in the replica-test pass of 2026-10-21 on build 03ac633. Each one has a regression test
that failed before the fix. Device: Linux, PySide6 offscreen.

Summary: 8 found (S1 0, S2 4, S3 4, S4 0), 8 fixed.

### BUG-001: characters outside Latin-1 silently lost on save

- Severity: S2
- Flow / case: F05 / F05-E1
- Screen: S13

Steps
1. Write a rung comment or symbol with an emoji or a non-Latin-1 character ("Señal ✓").
2. File → Save.

Expected: the user is told which characters cannot be stored.
Actual: they were saved as "?" with no warning.
Evidence: `tests/test_bugs.py::test_bug001_unsupported_characters_are_reported_on_save`
Status: fixed in abcc82d

### BUG-002: SYMBOLS section added to files that had none

- Severity: S3
- Flow / case: F02 / F02-E2
- Screen: S13

Steps
1. Open an .rsl without a SYMBOLS section.
2. Save.

Expected: byte-identical file.
Actual: an empty SYMBOLS section was appended.
Evidence: `tests/test_bugs.py::test_bug002_no_symbols_section_added_when_absent`
Status: fixed in abcc82d

### BUG-003: addresses outside the data table accepted at download

- Severity: S2
- Flow / case: F01 / F01-E2
- Screen: S04

Steps
1. Rung `MOV 1 N7:256` (or `XIC O:9/0`, `B3:300/1`, `T4:999.ACC`).
2. Download, RUN.

Expected: download refused with "out of range".
Actual: downloaded; the error appeared only at run time as a fault.
Evidence: `tests/test_bugs.py::test_bug003_addresses_outside_the_data_table_rejected_at_download`
Status: fixed in abcc82d

### BUG-004: bit instructions accepted on float elements

- Severity: S3
- Flow / case: F01 / F01-E3
- Screen: S07

Steps
1. XIC with operand `F8:0/1`.

Expected: "float elements have no bits".
Actual: accepted.
Evidence: `tests/test_bugs.py::test_bug004_float_file_has_no_bits`
Status: fixed in abcc82d

### BUG-005: bit cells in the data table accept any text as 1

- Severity: S3
- Flow / case: F03 / F03-E2
- Screen: S05

Steps
1. Data Table, B3, Binary.
2. Type "2" in a bit cell.

Expected: rejected; only 0 or 1.
Actual: bit set to 1.
Evidence: `tests/test_bugs_ui.py::test_bug005_bit_cells_accept_only_0_or_1`
Status: fixed in abcc82d

### BUG-006: out-of-range values in word and float cells wrap silently

- Severity: S3
- Flow / case: F03 / F03-E3
- Screen: S05

Steps
1. Data Table, N7, Hex: type 12345. Decimal: 40000 or -32769. Octal: 200000. F8: 1e40.

Expected: rejected, value unchanged.
Actual: value wrapped to 16 bits (float stored as inf).
Evidence: `tests/test_bugs_ui.py::test_bug006_word_cells_reject_out_of_range`, `test_bug006_float_cells_reject_out_of_range`
Status: fixed in abcc82d

### BUG-007: download keeps the previous program's data

- Severity: S2
- Flow / case: F02 / F02-E4
- Screen: S04

Steps
1. Download a counter program, let C5:0.ACC reach 7, write N7:50 = 3.
2. Download a different program.

Expected: data table starts clean (I/O kept), like a real download.
Actual: C5:0.ACC = 7 and N7:50 = 3 remained.
Evidence: `tests/test_bugs.py::test_bug007_download_clears_previous_program_data`
Status: fixed in abcc82d

### BUG-008: download while running leaves outputs on

- Severity: S2
- Flow / case: F02 / F02-E3
- Screen: S04

Steps
1. RUN a program with O:2/0 on.
2. Download another program without switching to PGM.

Expected: PLC goes to PGM and outputs turn off.
Actual: PLC in PGM but O:2/0 stayed on in the simulation.
Evidence: `tests/test_bugs.py::test_bug008_download_while_running_turns_outputs_off`
Status: fixed in abcc82d

## To check

- High-DPI and dark theme rendering on a real display (manual).
- Screen reader reading of ladder elements (only switches and lamps have accessible names).
