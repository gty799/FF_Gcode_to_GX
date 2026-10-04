from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from gcode_to_gx import GX_BMP_SIZE, GX_GCODE_OFFSET
from gcode_to_gx.gx_writer import convert_file, parse_header, validate_gx_layout
from gcode_to_gx.metadata import extract_metadata
from gcode_to_gx.printers import PRINTER_IDS, detect_dual_from_gcode, get_profile, resolve_profile
from gcode_to_gx.thumbnail import blank_bmp, extract_thumbnail_bmp


FIXTURE_DUAL = Path(__file__).parent / "fixtures" / "sample_dual.gcode"
FIXTURE_SINGLE = Path(__file__).parent / "fixtures" / "sample_single.gcode"


def test_metadata_dual():
    lines = FIXTURE_DUAL.read_text(encoding="utf-8").splitlines(keepends=True)
    meta = extract_metadata(lines, profile=get_profile("creator3pro"))
    assert meta.print_time == 3723
    assert meta.filament_right_mm == 1234
    assert meta.filament_left_mm == 678
    assert meta.layer_height_um == 200
    assert meta.bed_temp == 60
    assert meta.nozzle_right == 220
    assert meta.nozzle_left == 210
    assert meta.multi_extruder_type == 1
    assert meta.perimeter_shells == 3


def test_metadata_single_profile_zeros_left():
    lines = FIXTURE_DUAL.read_text(encoding="utf-8").splitlines(keepends=True)
    meta = extract_metadata(lines, profile=get_profile("adventurer5m"))
    assert meta.filament_right_mm == 1234
    assert meta.filament_left_mm == 0
    assert meta.nozzle_left == 0
    assert meta.multi_extruder_type == 0


def test_bmp_exact_size():
    assert len(blank_bmp()) == GX_BMP_SIZE
    lines = FIXTURE_DUAL.read_text(encoding="utf-8").splitlines(keepends=True)
    bmp = extract_thumbnail_bmp(lines)
    assert len(bmp) == GX_BMP_SIZE
    assert bmp[:2] == b"BM"


def test_convert_dual_creator3pro(tmp_path: Path):
    target = tmp_path / "job.gx"
    shutil.copy(FIXTURE_DUAL, target)
    profile = convert_file(str(target), printer_id="creator3pro")
    assert profile.id == "creator3pro"
    data = target.read_bytes()
    validate_gx_layout(data)
    assert len(data) > GX_GCODE_OFFSET
    header = parse_header(data)
    assert header.multi_extruder_type == 1
    assert header.filament_left_mm == 678
    assert header.nozzle_left == 210
    payload = data[GX_GCODE_OFFSET:]
    assert b"G28" in payload
    assert b"T1" in payload


def test_convert_creatorpro2_dual_uses_supplied_flashprint_header(tmp_path: Path):
    target = tmp_path / "creatorpro2.gx"
    shutil.copy(FIXTURE_DUAL, target)
    assert convert_file(str(target), printer_id="creatorpro2").id == "creatorpro2"
    data = target.read_bytes()
    validate_gx_layout(data)
    header = parse_header(data)
    assert header.multi_extruder_type == 1
    assert header.reserved1 == 0x0707
    assert header.filament_right_mm == 678
    assert header.filament_left_mm == 1234
    assert data[40:42] == b"\x01\x00"
    assert data[56:58] == b"\x07\x07"


def test_creatorpro2_reads_supplied_orca_preset_comments():
    lines = [
        ";machine_type: Creator Pro 2\n",
        ";layer_height: 0.2\n",
        ";perimeter_shells: 3\n",
        ";base_print_speed: 45\n",
        ";platform_temperature: 60\n",
        ";right_extruder_temperature: 210\n",
        ";left_extruder_temperature: 220\n",
        ";filament used [mm] = 1234, 678\n",  # Orca left, right
        ";nozzle_temperature = 220,210\n",  # Orca left, right
        "M118 X50 Y50 Z10 T0 T1\n",
    ]
    meta = extract_metadata(lines, profile=get_profile("creatorpro2"))
    assert meta.filament_right_mm == 678
    assert meta.filament_left_mm == 1234
    assert meta.nozzle_right == 210
    assert meta.nozzle_left == 220
    assert meta.layer_height_um == 200
    assert meta.perimeter_shells == 3
    assert meta.print_speed == 45
    assert meta.bed_temp == 60


def test_convert_creatorpro2_left_only_maps_single_metadata_to_t1(tmp_path: Path):
    target = tmp_path / "left.gx"
    target.write_text(
        "; filament used [mm] = 890\n"
        "; nozzle_temperature = 210\n"
        "M118 X0 Y0 Z150 T1\nM108 T1\nG1 X0 Y0 E1\n",
        encoding="utf-8",
    )
    convert_file(str(target), printer_id="creatorpro2")
    header = parse_header(target.read_bytes())
    assert header.filament_right_mm == 0
    assert header.filament_left_mm == 890
    assert header.nozzle_right == 0
    assert header.nozzle_left == 210
    assert header.multi_extruder_type == 1


def test_creatorpro2_right_only_keeps_single_metadata_on_t0(tmp_path: Path):
    target = tmp_path / "right.gx"
    target.write_text(
        "; filament used [mm] = 890\n"
        "; nozzle_temperature = 210\n"
        "M118 X0 Y0 Z150 T0\nM108 T0\nG1 X0 Y0 E1\n",
        encoding="utf-8",
    )
    convert_file(str(target), printer_id="creatorpro2")
    header = parse_header(target.read_bytes())
    assert header.filament_right_mm == 890
    assert header.filament_left_mm == 0
    assert header.nozzle_right == 210
    assert header.nozzle_left == 0


@pytest.mark.parametrize("mode_command", ["M109 T1", "M109 T2", "M118 X0 Y0 Z150 T0 T1 D2"])
def test_creatorpro2_rejects_unimplemented_parallel_modes(tmp_path: Path, mode_command: str):
    target = tmp_path / "parallel.gx"
    original = f"M118 X0 Y0 Z150 T0 T1\n{mode_command}\nG1 X0\n".encode()
    target.write_bytes(original)
    with pytest.raises(ValueError, match="mirror/duplicate"):
        convert_file(str(target), printer_id="creatorpro2")
    assert target.read_bytes() == original


def test_convert_single_adventurer5m(tmp_path: Path):
    target = tmp_path / "single.gx"
    shutil.copy(FIXTURE_SINGLE, target)
    profile = convert_file(str(target), printer_id="adventurer5m")
    assert profile.id == "adventurer5m"
    data = target.read_bytes()
    validate_gx_layout(data)
    header = parse_header(data)
    assert header.multi_extruder_type == 0
    assert header.filament_right_mm == 890
    assert header.filament_left_mm == 0
    assert header.nozzle_right == 210
    assert header.nozzle_left == 0
    assert header.reserved1 == 1


def test_auto_detect_dual_and_single():
    dual_lines = FIXTURE_DUAL.read_text(encoding="utf-8").splitlines(keepends=True)
    single_lines = FIXTURE_SINGLE.read_text(encoding="utf-8").splitlines(keepends=True)
    assert detect_dual_from_gcode(dual_lines) is True
    assert detect_dual_from_gcode(single_lines) is False
    assert resolve_profile(lines=dual_lines).id == "generic_dual"
    assert resolve_profile(lines=single_lines).id == "generic_single"


def test_env_printer_overrides_auto(monkeypatch: pytest.MonkeyPatch):
    dual_lines = FIXTURE_DUAL.read_text(encoding="utf-8").splitlines(keepends=True)
    monkeypatch.setenv("GCODE_TO_GX_PRINTER", "adventurer3")
    assert resolve_profile(lines=dual_lines).id == "adventurer3"
    monkeypatch.delenv("GCODE_TO_GX_PRINTER")
    assert resolve_profile(printer_id="creator3pro", lines=dual_lines).id == "creator3pro"


def test_all_printer_ids_registered():
    expected = {
        "adventurer3",
        "adventurer4",
        "adventurer5m",
        "creator3pro",
        "creatorpro2",
        "generic_single",
        "generic_dual",
    }
    assert set(PRINTER_IDS) == expected


def test_cli_main(tmp_path: Path):
    from gcode_to_gx.cli import main

    target = tmp_path / "out.gx"
    shutil.copy(FIXTURE_DUAL, target)
    assert main([str(target)]) == 0
    validate_gx_layout(target.read_bytes())
    assert main([]) == 2


def test_cli_printer_flag(tmp_path: Path):
    from gcode_to_gx.cli import main

    target = tmp_path / "out.gx"
    shutil.copy(FIXTURE_SINGLE, target)
    assert main(["--printer", "adventurer4", str(target)]) == 0
    header = parse_header(target.read_bytes())
    assert header.multi_extruder_type == 0


def test_calibrate_missing_reference(tmp_path: Path):
    target = tmp_path / "ours.gx"
    shutil.copy(FIXTURE_DUAL, target)
    convert_file(str(target), printer_id="generic_dual")
    validate_gx_layout(target.read_bytes())
