"""Hermes Print Automation - Physical Printer Spooler Service.

Executes direct physical printing via SumatraPDF CLI on Windows or CUPS `lp` on Linux.
Includes auto-detection of default printers, executable resolution, and simulation mode.
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.config import settings
from app.models import PrintJobResult

logger = logging.getLogger("hermes.printer")


def find_sumatrapdf_executable() -> Optional[str]:
    """Locate SumatraPDF.exe in system PATH or common Windows installation directories."""
    # 1. Configured path
    if settings.SUMATRAPDF_PATH and os.path.exists(settings.SUMATRAPDF_PATH):
        return str(Path(settings.SUMATRAPDF_PATH).resolve())

    # 2. In PATH
    which_path = shutil.which("SumatraPDF.exe") or shutil.which("SumatraPDF")
    if which_path:
        return which_path

    # 3. Common Windows install locations
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")

    candidates = [
        Path(program_files) / "SumatraPDF" / "SumatraPDF.exe",
        Path(program_files_x86) / "SumatraPDF" / "SumatraPDF.exe",
        Path(local_app_data) / "SumatraPDF" / "SumatraPDF.exe",
        Path(os.getcwd()) / "bin" / "SumatraPDF.exe",
    ]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())

    return None


def get_available_printers() -> Tuple[List[str], Optional[str]]:
    """List installed system printers and identify the OS default printer."""
    printers: List[str] = []
    default_printer: Optional[str] = None

    if sys.platform.startswith("win") or settings.PRINTER_OS.lower() == "windows":
        try:
            # Query Windows printers via PowerShell
            ps_cmd = (
                "Get-CimInstance -ClassName Win32_Printer | "
                "Select-Object Name, Default | ConvertTo-Json"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                try:
                    data = json.loads(result.stdout)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        name = item.get("Name")
                        if name:
                            printers.append(name)
                            if item.get("Default") is True:
                                default_printer = name
                except json.JSONDecodeError:
                    pass
        except Exception as exc:
            logger.warning("[PRINTER] Could not list Windows printers via PowerShell: %s", exc)

    elif sys.platform.startswith("linux") or settings.PRINTER_OS.lower() == "linux":
        try:
            # Check CUPS printers
            result = subprocess.run(
                ["lpstat", "-p", "-d"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("printer "):
                        parts = line.split()
                        if len(parts) >= 2:
                            printers.append(parts[1])
                    elif line.startswith("system default destination:"):
                        default_printer = line.split(":")[-1].strip()
        except Exception as exc:
            logger.warning("[PRINTER] Could not list Linux CUPS printers: %s", exc)

    return printers, default_printer


def build_sumatra_print_settings(
    copies: int = 1,
    color_mode: str = "auto",
    page_range: str = "all",
    paper_size: str = "A4",
    orientation: str = "auto"
) -> str:
    """Build the `-print-settings` parameter value for SumatraPDF CLI."""
    settings_items: List[str] = []

    # Number of copies
    if copies > 1:
        settings_items.append(f"copies={copies}")

    # Color vs monochrome
    mode_clean = color_mode.lower()
    if mode_clean == "bw" or mode_clean == "monochrome":
        settings_items.append("monochrome")
    elif mode_clean == "color":
        settings_items.append("color")

    # Page range (e.g. '1-5', '1,3,5')
    if page_range and page_range.lower() not in ("all", "semua", "*"):
        settings_items.append(page_range.replace(" ", ""))

    # Paper size (e.g. 'paper=A4')
    if paper_size and "custom" not in paper_size.lower():
        clean_size = paper_size.split()[0].replace("/", "")
        settings_items.append(f"paper={clean_size}")

    # Orientation
    orient_clean = orientation.lower()
    if "lanskap" in orient_clean or "landscape" in orient_clean:
        settings_items.append("landscape")
    elif "potret" in orient_clean or "portrait" in orient_clean:
        settings_items.append("portrait")

    return ",".join(settings_items)


def execute_print_windows(
    file_path: str,
    printer_name: Optional[str] = None,
    copies: int = 1,
    color_mode: str = "auto",
    page_range: str = "all",
    paper_size: str = "A4",
    orientation: str = "auto"
) -> PrintJobResult:
    """Send print job to a physical printer on Windows using SumatraPDF or PowerShell fallback."""
    abs_file_path = str(Path(file_path).resolve())
    target_printer = printer_name or settings.PRINTER_NAME

    # Discover default printer if not specified
    if not target_printer:
        _, detected_default = get_available_printers()
        target_printer = detected_default or "Default Printer"

    sumatra_exe = find_sumatrapdf_executable()
    print_settings_str = build_sumatra_print_settings(
        copies=copies,
        color_mode=color_mode,
        page_range=page_range,
        paper_size=paper_size,
        orientation=orientation
    )

    if sumatra_exe:
        # SumatraPDF Command Line Arguments:
        # SumatraPDF.exe -print-to "<PrinterName>" [-print-settings "<settings>"] -silent "<FilePath>"
        cmd: List[str] = [sumatra_exe]
        if target_printer and target_printer != "Default Printer":
            cmd.extend(["-print-to", target_printer])
        else:
            cmd.append("-print-to-default")

        if print_settings_str:
            cmd.extend(["-print-settings", print_settings_str])

        cmd.extend(["-silent", abs_file_path])
        cmd_str = " ".join([f'"{c}"' if " " in c else c for c in cmd])

        # Handle simulation mode
        if settings.PRINT_SIMULATION_MODE:
            logger.info("[SIMULATION MODE] Print command generated: %s", cmd_str)
            return PrintJobResult(
                success=True,
                command_executed=cmd_str,
                printer_used=target_printer,
                copies=copies,
                color_mode=color_mode,
                pages=page_range,
                is_simulated=True
            )

        try:
            logger.info("[PRINTER] Running SumatraPDF print: %s", cmd_str)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
            if result.returncode == 0:
                return PrintJobResult(
                    success=True,
                    command_executed=cmd_str,
                    printer_used=target_printer,
                    copies=copies,
                    color_mode=color_mode,
                    pages=page_range,
                    is_simulated=False
                )
            else:
                return PrintJobResult(
                    success=False,
                    command_executed=cmd_str,
                    printer_used=target_printer,
                    copies=copies,
                    color_mode=color_mode,
                    pages=page_range,
                    error_message=f"SumatraPDF exited with code {result.returncode}: {result.stderr}",
                    is_simulated=False
                )
        except Exception as exc:
            logger.error("[PRINTER] Failed to execute SumatraPDF: %s", exc)
            return PrintJobResult(
                success=False,
                command_executed=cmd_str,
                printer_used=target_printer,
                copies=copies,
                color_mode=color_mode,
                pages=page_range,
                error_message=str(exc),
                is_simulated=False
            )

    else:
        # Fallback to Windows PowerShell Verb PrintTo
        logger.warning(
            "[PRINTER] SumatraPDF.exe was not found. Using Windows PowerShell Print verb fallback."
        )
        if target_printer and target_printer != "Default Printer":
            ps_script = f'Start-Process -FilePath "{abs_file_path}" -Verb PrintTo -ArgumentList "\"{target_printer}\"" -PassThru | Out-Null'
        else:
            ps_script = f'Start-Process -FilePath "{abs_file_path}" -Verb Print -PassThru | Out-Null'

        cmd_str = f"powershell -Command {ps_script}"

        if settings.PRINT_SIMULATION_MODE:
            logger.info("[SIMULATION MODE] Fallback command: %s", cmd_str)
            return PrintJobResult(
                success=True,
                command_executed=cmd_str,
                printer_used=target_printer,
                copies=copies,
                color_mode=color_mode,
                pages=page_range,
                is_simulated=True
            )

        try:
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], timeout=30, check=False)
            return PrintJobResult(
                success=res.returncode == 0,
                command_executed=cmd_str,
                printer_used=target_printer,
                copies=copies,
                color_mode=color_mode,
                pages=page_range,
                error_message=None if res.returncode == 0 else "PowerShell Start-Process returned non-zero code.",
                is_simulated=False
            )
        except Exception as exc:
            return PrintJobResult(
                success=False,
                command_executed=cmd_str,
                printer_used=target_printer,
                copies=copies,
                color_mode=color_mode,
                pages=page_range,
                error_message=f"Windows print fallback failed: {str(exc)}",
                is_simulated=False
            )


def execute_print_linux(
    file_path: str,
    printer_name: Optional[str] = None,
    copies: int = 1,
    color_mode: str = "auto",
    page_range: str = "all"
) -> PrintJobResult:
    """Send print job to physical CUPS spooler on Linux."""
    abs_file_path = str(Path(file_path).resolve())
    target_printer = printer_name or settings.PRINTER_NAME

    if not target_printer:
        _, detected_default = get_available_printers()
        target_printer = detected_default or "default"

    cmd: List[str] = ["lp"]
    if target_printer:
        cmd.extend(["-d", target_printer])
    if copies > 1:
        cmd.extend(["-n", str(copies)])
    if page_range and page_range.lower() not in ("all", "semua", "*"):
        cmd.extend(["-o", f"page-ranges={page_range}"])

    if color_mode.lower() in ("bw", "monochrome"):
        cmd.extend(["-o", "ColorModel=Gray"])
    elif color_mode.lower() == "color":
        cmd.extend(["-o", "ColorModel=CMYK"])

    cmd.append(abs_file_path)
    cmd_str = " ".join(cmd)

    if settings.PRINT_SIMULATION_MODE:
        logger.info("[SIMULATION MODE] Linux lp command: %s", cmd_str)
        return PrintJobResult(
            success=True,
            command_executed=cmd_str,
            printer_used=target_printer,
            copies=copies,
            color_mode=color_mode,
            pages=page_range,
            is_simulated=True
        )

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        return PrintJobResult(
            success=res.returncode == 0,
            command_executed=cmd_str,
            printer_used=target_printer,
            copies=copies,
            color_mode=color_mode,
            pages=page_range,
            error_message=None if res.returncode == 0 else res.stderr,
            is_simulated=False
        )
    except Exception as exc:
        return PrintJobResult(
            success=False,
            command_executed=cmd_str,
            printer_used=target_printer,
            copies=copies,
            color_mode=color_mode,
            pages=page_range,
            error_message=str(exc),
            is_simulated=False
        )


def print_document(
    file_path: str,
    copies: int = 1,
    color_mode: str = "auto",
    page_range: str = "all",
    paper_size: str = "A4",
    orientation: str = "auto",
    printer_name: Optional[str] = None
) -> PrintJobResult:
    """Dispatch printing to the appropriate OS handler."""
    os_target = settings.PRINTER_OS.lower()
    if os_target == "linux" or sys.platform.startswith("linux"):
        return execute_print_linux(
            file_path=file_path,
            printer_name=printer_name,
            copies=copies,
            color_mode=color_mode,
            page_range=page_range
        )
    else:
        return execute_print_windows(
            file_path=file_path,
            printer_name=printer_name,
            copies=copies,
            color_mode=color_mode,
            page_range=page_range,
            paper_size=paper_size,
            orientation=orientation
        )
