"""Парсинг метаданных из комментариев Orca G-code."""

from __future__ import annotations

import re
from dataclasses import dataclass

from gcode_to_gx.printers.registry import PrinterProfile


@dataclass
class PrintMetadata:
    print_time: int = 0
    filament_right_mm: int = 0
    filament_left_mm: int = 0
    layer_height_um: int = 0
    print_speed: int = 60
    bed_temp: int = 0
    nozzle_right: int = 0
    nozzle_left: int = 0
    multi_extruder_type: int = 1
    perimeter_shells: int = 2
    header_marker: int = 1


def _parse_float_token(raw: str) -> float:
    return float(raw.strip().replace(",", "."))


def _parse_int_list(value: str) -> list[int]:
    """Разбор '220,210' или '220.0, 210.0' или одного значения с десятичной запятой."""
    parts = [p.strip() for p in value.split(",")]
    if len(parts) >= 2:
        try:
            return [int(_parse_float_token(p)) for p in parts if p]
        except ValueError:
            pass
    try:
        return [int(_parse_float_token(value))]
    except ValueError:
        return []


def _parse_print_time(value: str) -> int:
    h = m = s = 0
    for part in value.strip().split():
        if part.endswith("h"):
            h = int(part[:-1] or "0")
        elif part.endswith("m"):
            m = int(part[:-1] or "0")
        elif part.endswith("s"):
            s = int(part[:-1] or "0")
    return h * 3600 + m * 60 + s


def extract_metadata(
    lines: list[str],
    profile: PrinterProfile | None = None,
) -> PrintMetadata:
    meta = PrintMetadata()
    filament_count = 0
    nozzle_count = 0
    explicit_right_temp: int | None = None
    explicit_left_temp: int | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(";"):
            continue
        body = stripped[1:].strip()
        separator = "=" if "=" in body else ":" if ":" in body else None
        if separator is None:
            continue
        key, _, raw = body.partition(separator)
        key = key.strip().lower()
        value = raw.strip()

        if key.startswith("estimated printing time (normal mode)"):
            meta.print_time = _parse_print_time(value)
        elif key.startswith("filament used [mm]"):
            vals = _parse_int_list(value)
            filament_count = len(vals)
            if vals:
                meta.filament_right_mm = vals[0]
            if len(vals) > 1:
                meta.filament_left_mm = vals[1]
        elif key == "layer_height":
            try:
                meta.layer_height_um = int(_parse_float_token(value.split()[0]) * 1000)
            except (ValueError, IndexError):
                pass
        elif key.startswith("machine_max_speed_x") or key in ("perimeter_speed", "base_print_speed"):
            vals = _parse_int_list(value)
            if vals:
                # Orca часто даёт пару лимитов; берём разумную скорость печати
                meta.print_speed = vals[-1] if len(vals) > 1 else vals[0]
        elif key in ("first_layer_bed_temperature", "bed_temperature", "platform_temperature"):
            vals = _parse_int_list(value)
            if vals:
                meta.bed_temp = vals[0]
        elif key in ("nozzle_temperature", "first_layer_temperature", "temperature"):
            vals = _parse_int_list(value)
            nozzle_count = len(vals)
            if vals:
                meta.nozzle_right = vals[0]
            if len(vals) > 1:
                meta.nozzle_left = vals[1]
        elif key == "right_extruder_temperature":
            vals = _parse_int_list(value)
            if vals:
                explicit_right_temp = vals[0]
        elif key == "left_extruder_temperature":
            vals = _parse_int_list(value)
            if vals:
                explicit_left_temp = vals[0]
        elif key in ("wall_loops", "wall_line_count", "perimeter_shells", "perimeters"):
            vals = _parse_int_list(value)
            if vals:
                meta.perimeter_shells = vals[0]

    if meta.print_time < 1:
        meta.print_time = 1

    if profile is not None:
        apply_profile(meta, profile)
        if profile.id == "creatorpro2":
            # The supplied Orca preset lists extruder 0 (physical left/T1)
            # before extruder 1 (physical right/T0).
            left_only = _creatorpro2_left_only(lines)
            if filament_count > 1:
                meta.filament_right_mm, meta.filament_left_mm = (
                    meta.filament_left_mm,
                    meta.filament_right_mm,
                )
            if nozzle_count > 1:
                meta.nozzle_right, meta.nozzle_left = meta.nozzle_left, meta.nozzle_right
            elif left_only and nozzle_count == 1:
                meta.nozzle_left, meta.nozzle_right = meta.nozzle_right, 0
            if left_only and filament_count == 1:
                meta.filament_left_mm, meta.filament_right_mm = meta.filament_right_mm, 0
            if explicit_right_temp is not None:
                meta.nozzle_right = explicit_right_temp
            if explicit_left_temp is not None:
                meta.nozzle_left = explicit_left_temp

    return meta


def apply_profile(meta: PrintMetadata, profile: PrinterProfile) -> PrintMetadata:
    """Применяет dual/single флаги профиля к уже распарсенным метаданным."""
    meta.multi_extruder_type = profile.multi_extruder_type
    meta.header_marker = profile.header_marker
    if not profile.dual:
        meta.filament_left_mm = 0
        meta.nozzle_left = 0
    return meta


def _creatorpro2_left_only(lines: list[str]) -> bool:
    """Read the Creator Pro 2's M118 enabled-head declaration, if present."""
    for line in lines:
        command = line.split(";", 1)[0].strip().upper()
        if not re.match(r"^M118\b", command):
            continue
        tools = set(re.findall(r"\bT([01])\b", command))
        if tools:
            return tools == {"1"}
    return False
