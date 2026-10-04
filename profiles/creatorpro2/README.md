# Flashforge Creator Pro 2 + Orca Slicer

The converter supports **normal** Creator Pro 2 jobs: right head (T0), left
head (T1), and independent dual extrusion. It follows the supplied Orca preset:
Orca extruder 0 is physical left/T1 and Orca extruder 1 is physical right/T0.
The GX header mode and last two bytes match the user's existing
`ffcp2_orca_sd.py` exporter (`1`, `07 07`).

For file conversion in Orca, use `--printer creatorpro2` in the
**Post-processing scripts** field and set the output filename extension to
`.gx`. For example, on Windows:

```text
"C:\path\to\gcode_to_gx.exe" --printer creatorpro2
```

Orca appends the temporary file path. Do not add a path to this command.

If you already use `ffcp2_export_dialog.bat` with `ffcp2_orca_sd.py`, that
pipeline builds and uploads GX files itself. You can keep using it without
adding this converter. Its worker also accepts an already wrapped GX file and
passes it through without adding a second header.

## Machine G-code still matters

The converter adds the Flashforge GX header and thumbnail. It does not convert
Marlin tool changes or heating commands into the Creator Pro 2 dialect. Use a
Creator Pro 2 machine preset in Orca and inspect the sliced G-code before
printing. For normal jobs, the preset should include:

- `M118 ... T0` for right only, `M118 ... T1` for left only, or
  `M118 ... T0 T1` for independent dual printing, with your machine's correct
  X/Y/Z limits. This also lets the converter assign a single filament/temperature
  value to the left head when only T1 is enabled.
- `M108 T0` / `M108 T1` to select and park the physical heads. The supplied
  preset also emits bare `T0` / `T1` for Orca's temperature visualization;
  those are not its physical tool-change commands.
- The Creator Pro 2 heating and homing sequence used by your working machine
  preset. In known working community profiles this includes `M140`/`M104` with
  explicit `T` arguments, `M7`/`M6` heat waits, `G28`, and `M132`.

The [community Creator Pro 2 PrusaSlicer profile](https://github.com/Jacotheron/FlashForge-CreatorPro2-PS-Profile)
documents the machine commands, but its published header values differ from
the user's calibrated exporter. Its presets are for **PrusaSlicer**, so adapt
placeholders before using them in Orca.

Mirror and duplicate/ditto modes are not supported. The converter rejects
their `M118 ... D1/D2` or `M109 T1/T2` commands rather than making a GX file
with the wrong mode header or a missing calibration pad.

Automated tests verify the header, payload layout, and Orca extruder mapping
against the supplied profile and exporter code. A physical Creator Pro 2 print
has not been tested here. Start with a small normal-mode print, and compare its
header to a working FlashPrint `.gx` using `scripts/calibrate_header.py` if the
printer rejects the file. Keep the filename short if the printer shows “File
open failed.”
