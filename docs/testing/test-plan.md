# Test plan: plc-sim

Build: 03ac633 + working tree  Date: 2026-10-21  Env: local, PySide6 offscreen, pytest-qt

Desktop app: the e2e layer is pytest-qt driving `MainWindow` (no browser, so no Playwright/axe).
Specs: `tests/e2e/test_flows.py` (flows), `tests/test_bugs.py` and `tests/test_bugs_ui.py` (regressions).
Scans are driven by the test (`plc.tick`), not by the wall clock.

| case | flow | type | steps | expected | auto | result |
| --- | --- | --- | --- | --- | --- | --- |
| F01-H1 | first program | happy | new rung, XIC I:1/0, OTE O:2/0, download, RUN, click switch twice | lamp O:2/0 follows the switch | e2e | pass |
| F01-N1 | | negative: address left as "?" | insert XIC, download | "not downloaded" dialog, PLC stays undownloaded | e2e | pass |
| F01-N2 | | negative: word on bit instruction | XIC N7:0, download | dialog suggests N7:0/0 | e2e | pass |
| F01-E1 | | edge: edit while in RUN | RUN, insert a rung | status "edited, download to apply" | e2e | pass |
| F01-E2 | | edge: address outside the data table | MOV 1 N7:256, XIC O:9/0, T4:999.ACC | rejected at download (BUG-003) | unit | pass |
| F01-E3 | | edge: bit of a float element | XIC F8:0/1 | rejected (BUG-004) | unit | pass |
| F01-E4 | | edge: keyboard only | build seal-in with keys | same as mouse | e2e (test_ui_editor) | pass |
| F02-H1 | open example and run | happy | open start-stop.rsl, download, RUN, start, stop | NC stop wired from symbols, seal-in, stop drops motor | e2e | pass |
| F02-E1 | | edge: CRLF / LF | open both | same program | e2e | pass |
| F02-E2 | | edge: missing SYMBOLS section | load, save | no SYMBOLS added (BUG-002) | unit | pass |
| F02-E3 | | edge: download while running | RUN with outputs on, download other program | PGM, outputs off (BUG-008) | unit | pass |
| F02-E4 | | edge: download after another program | counter ACC 7, N7:50 = 3, download new | data from old program gone (BUG-007) | unit | pass |
| F02-N1 | | negative: unsupported instruction (PID) | open | reported on open or download, no RUN | e2e | pass |
| F02-N2 | | negative: binary garbage | open | dialog, path unchanged | e2e | pass |
| F03-H1 | debug with data table | happy | timer-counter, Enable on, 1.51 s | T4:0 ACC = 15 in table | e2e | pass |
| F03-E1 | | edge: radix change, edit while running | Hex, N7:0 = FF in RUN | value 255, shown as FF | e2e | pass |
| F03-E2 | | edge: bit cell "2" | type 2 in a B3 bit | rejected (BUG-005) | ui | pass |
| F03-E3 | | edge: out-of-range word/float | 12345 hex, 40000 dec, 1e40 float | rejected, value unchanged (BUG-006) | ui | pass |
| F04-H1 | change switch type | happy | each of the 4 types, press and release | NO/NC signal, momentary returns | e2e | pass |
| F05-H1 | save | happy | open sample, save to new path | byte-identical, title clean | e2e | pass |
| F05-E1 | | edge: accents and emoji | comment "Válvula ñ 🚀", save | accents kept, emoji reported and saved as ? (BUG-001) | e2e | pass |
| F05-N1 | | negative: unwritable path | save to missing folder | "Could not save", still dirty | e2e | pass |
| F06-H1 | clear data table | happy | write N7, C5 ACC, B3 bit, clear | all zero | e2e | pass |
| F07-H1 | silo / traffic exercises | happy | solutions 08-silo-continuous, 10-traffic-light, RUN 5 s | no fault | e2e | pass |
| F07-H2 | | happy: new program for exercise | Exercises panel, silo lab, "New program" | sim switches, lab symbols loaded | e2e | pass |
| F07-H3 | | happy: every written requirement | tests/test_labs.py | all 10 labs meet their spec | unit | pass |
| F08-H1 | subroutines | happy | JSR U:3, SBR drives O:2/3 | lamp on | e2e | pass |
| F08-N1 | | negative: JSR to missing file | JSR U:5 | "subroutine file 5 does not exist" | e2e | pass |

Not applicable (web-only edge cases): two tabs, back/refresh, network, sessions, second user, payments.

Manual (needs a real display): high-DPI rendering, dark theme contrast, screen reader names
(`setAccessibleName` is set on every switch), drag of rungs with the mouse.
