"""
Wrapper pour l'autopatcher Lenovo.
"""
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional


class AutopatchError(Exception):
    pass


def patch_rom(
    autopatcher_dir: str,
    rom_path: str,
    on_progress: Optional[Callable[[str], None]] = None,
) -> str:
    autopatcher_dir = Path(autopatcher_dir)
    rom_path = Path(rom_path).absolute()
    
    autopatch_py = autopatcher_dir / 'patch' / 'autopatch.py'
    
    if not autopatch_py.exists():
        raise AutopatchError(f"autopatch.py introuvable : {autopatcher_dir}")
    if not rom_path.exists():
        raise AutopatchError(f"ROM introuvable : {rom_path}")
    
    flags = 0
    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
        flags = subprocess.CREATE_NO_WINDOW
    
    cmd = [sys.executable, str(autopatch_py), str(rom_path)]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(autopatcher_dir),
        creationflags=flags,
    )
    
    output_lines = []
    for line in iter(process.stdout.readline, ''):
        output_lines.append(line.rstrip())
        if on_progress:
            on_progress(line.rstrip())
    process.wait()
    
    full_output = '\n'.join(output_lines)
    
    if process.returncode != 0:
        raise AutopatchError(f"Autopatcher a échoué (code {process.returncode}) :\n{full_output}")
    
    if 'corrupted' in full_output.lower() or 'aborting' in full_output.lower():
        raise AutopatchError(f"Dump corrompu détecté :\n{full_output}")
    
    patched_path = rom_path.parent / f"{rom_path.stem}_PATCHED{rom_path.suffix}"
    
    if not patched_path.exists():
        raise AutopatchError(f"Fichier patché non créé : {patched_path}")
    
    return str(patched_path)
