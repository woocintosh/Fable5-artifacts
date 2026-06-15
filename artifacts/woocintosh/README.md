# Civilization V Save File Gold Editor

**Contributor:** [@woocintosh](https://github.com/woocintosh)  
**Date:** June 2026  
**Time Fable 5 spent on it:** ~1 hour  
**Did it work?** Yes.

---

## What is it?

A Python script that edits the gold value in a Civilization V save file (`.Civ5Save`).

No dependencies. Standard library only. Works on Mac, Windows, and Linux.

## What I asked Fable 5 to do

I uploaded a `.Civ5Save` file and asked Fable 5 to:

1. Figure out how the save file is structured
2. Find where the gold value is stored
3. Write a script to change it

I gave it nothing else. No documentation, no hints about the format.

## What Fable 5 actually did

Fable 5 spent about an hour reverse-engineering the file format from scratch inside a Cowork session:

- Discovered the file body is split into 64KB zlib-compressed chunks with 4-byte length prefixes
- Figured out that gold is stored as `(gold × 100)` as an int32
- Found that the value is preceded by a `[0, 1]` int32 signature
- Used the capital city name as an anchor to locate the player's treasury (vs. AI civs)
- Added patch verification to ensure no unintended bytes were changed

The working folder still has the test files from the iteration process: `testA0b.Civ5Save`, `test11b.Civ5Save`, etc.

## How to use it

```bash
python3 civ5_gold_editor.py <savefile> --set <target_gold> --capital <capital_city_name>

# Example
python3 civ5_gold_editor.py MySave --set 500000 --capital Madrid
```

The original file is never overwritten. Output is saved as a new file.

## Files

- `civ5_gold_editor.py` — the editor

---

*Built with Claude Fable 5 in a Cowork session, June 2026.*  
*Fable 5 was taken down by U.S. export controls 3 days after this was made.*
