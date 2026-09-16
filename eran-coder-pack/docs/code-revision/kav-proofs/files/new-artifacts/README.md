# kav/legacy — retired rulers and the backups they were replaced from

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

KAV-10, 2026-09-06. These five files sat in the organ's own directory beside the live
ruler, all runnable, none imported by anything. `connect2.cpython-312.pyc` was dated
2026-09-05 09:23 — it was still being RUN two hours after joiner.py shipped at 07:22.
They are kept for their record and moved out of reach; their `__main__` blocks now
refuse to run.

| file | what it measured | why it was retired |
|---|---|---|
| `connect.py` | the first joining experiment: a world-frame surface walk, with its own `table_and_faces`. | Superseded by `joiner.py` on the vertex-indexed tongue (2026-09-03). A different tongue — its numbers are not comparable to today's. |
| `connect2.py` | gate 2 as `solid = watertight == tried`. | **REFUTED.** Watertight alone let a sixth of a box pass; measured 2026-09-06, the flat close-the-hole floor is 3/3 watertight at volume x0.167–x0.300 and 0/3 right solids. It also carried a SECOND, contradicting HELD (`plate, stack, pinch-rail`). The live gate is watertight **AND** the truth's face count **AND** the truth's volume within 1%. |
| `connect2.py.bak-worldframe` | connect2 before the frame change. | backup of a retired file |
| `ruler.py.bak-gate2-20260905` | the ruler before the wide denominator | backup; git and `tests/test_joiner.py`'s `GATE2_DECISION_20260905` hold the record |
| `test_joiner.py.bak-gate2-20260905` | the tests before the wide denominator | backup |

Nothing here is on any import path. If you want a number out of KAV, run
`python ruler.py` (or `python ruler.py --wide`) in the directory above.
