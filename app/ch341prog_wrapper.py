"""
Wrapper Python pour ch341prog (alternative a flashrom).

ch341prog a un avantage majeur sur flashrom 1.4 :
- Il utilise fflush(stdout) apres chaque update de progression
- Le format de sortie est "Bytes: N (X%), Time: T, ETA: E\\r" en temps reel
- Pas de bufferisation, on voit la progression seconde par seconde

Le binaire est compile depuis ch341prog-master 25xx (sources C dans le zip),
patche pour Windows (sigaction → SetConsoleCtrlHandler).

Format de sortie :
  Device reported its revision [0.00]
  Manufacturer ID: ef
  Memory Type: 4018
  Capacity: 18
  Read started!
  Bytes: 1048576 (6%),  Time: 8, ETA: 125
  Bytes: 2097152 (12%), Time: 16, ETA: 117
  ...
  Total:  131 sec,  average speed  125000  bytes per second.
"""
import subprocess
import re
import threading
from pathlib import Path
from typing import Callable, Optional


class Ch341progError(Exception):
    pass


class Ch341progNotFoundError(Ch341progError):
    """Le CH341A est branche mais ch341prog n'arrive pas a communiquer."""
    pass


class Ch341progDriverError(Ch341progError):
    """Driver libusb non configure (WinUSB manquant)."""
    pass


class Ch341progWrapper:
    """
    Wrapper pour ch341prog.exe (CLI compatible CH341A).
    
    Bytes par seconde typique : ~125 KB/s.
    Une puce 16 Mo prend ~2 min 11 sec.
    """
    
    def __init__(self, ch341prog_path: str = 'ch341prog.exe'):
        self.ch341prog_path = ch341prog_path
    
    def _run_with_progress(
        self,
        cmd: list,
        on_log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int, int, int, int], None]] = None,
    ) -> tuple:
        """
        Lance ch341prog et parse la progression en temps reel.
        
        Args:
            cmd: commande complete
            on_log: callback ligne par ligne (logs visibles)
            on_progress: callback(bytes_done, percent, elapsed_sec, eta_sec)
        
        Returns:
            (returncode, output_complet)
        """
        flags = 0
        if hasattr(subprocess, 'CREATE_NO_WINDOW'):
            flags = subprocess.CREATE_NO_WINDOW
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,  # pas de bufferisation cote Python
            creationflags=flags,
        )
        
        output_lines = []
        
        # Pattern de progression : "Bytes: N (X%),  Time: T, ETA: E"
        progress_re = re.compile(
            rb'Bytes:\s*(\d+)\s*\((\d+)%\)\s*,\s*Time:\s*(\d+)\s*,\s*ETA:\s*(-?\d+)'
        )
        
        current_line = bytearray()
        last_progress = None
        
        while True:
            ch = process.stdout.read(1)
            if not ch:
                break
            
            # ch341prog termine ses updates de progression par \r (pas \n)
            # et les autres lignes par \n
            if ch in (b'\n', b'\r'):
                if current_line:
                    line_bytes = bytes(current_line)
                    
                    # Tenter de parser une ligne de progression
                    m = progress_re.search(line_bytes)
                    if m:
                        bytes_done = int(m.group(1))
                        percent = int(m.group(2))
                        elapsed = int(m.group(3))
                        eta = int(m.group(4))
                        # Eviter les updates redondantes
                        if (bytes_done, percent) != last_progress:
                            last_progress = (bytes_done, percent)
                            if on_progress:
                                try:
                                    on_progress(bytes_done, percent, elapsed, eta)
                                except Exception:
                                    pass
                    else:
                        # Ligne de log normale
                        try:
                            line = line_bytes.decode('utf-8', errors='replace').rstrip()
                        except Exception:
                            line = line_bytes.decode('latin-1', errors='replace').rstrip()
                        if line:
                            output_lines.append(line)
                            if on_log:
                                try:
                                    on_log(line)
                                except Exception:
                                    pass
                    
                    current_line = bytearray()
            else:
                current_line.extend(ch)
        
        # Reste de la derniere ligne
        if current_line:
            line = bytes(current_line).decode('utf-8', errors='replace').rstrip()
            if line:
                output_lines.append(line)
                if on_log:
                    try:
                        on_log(line)
                    except Exception:
                        pass
        
        process.wait()
        return process.returncode, '\n'.join(output_lines)
    
    def detect_chip(self, on_log: Optional[Callable] = None) -> dict:
        """
        Detecte le CH341A et la puce SPI.
        
        Returns: dict avec 'manufacturer_id', 'memory_type', 'capacity', 'chip_name'
        """
        cmd = [self.ch341prog_path, '-i']
        returncode, output = self._run_with_progress(cmd, on_log=on_log)
        
        output_lower = output.lower()
        
        # Cas 1 : driver pas installe
        if "couldn't open device" in output_lower or "couldn't initialise libusb" in output_lower:
            raise Ch341progDriverError(
                "CH341A introuvable ou driver libusb non configure.\n"
                "Verifie que le CH341A est branche en USB et que le driver "
                "WinUSB a ete installe via Zadig.\n\n"
                f"ch341prog output:\n{output[-500:]}"
            )
        
        # Cas 2 : puce non trouvee
        if 'chip not found' in output_lower or 'missed in ch341a' in output_lower:
            raise Ch341progNotFoundError(
                "Aucune puce SPI detectee.\n"
                "Verifie l'orientation du clip SOIC-8 "
                "(ligne rouge ↔ point sur la puce).\n\n"
                f"ch341prog output:\n{output[-500:]}"
            )
        
        # Parse les infos chip
        result = {}
        m = re.search(r'Manufacturer ID:\s*([0-9a-f]+)', output, re.IGNORECASE)
        if m:
            result['manufacturer_id'] = m.group(1).lower()
        m = re.search(r'Memory Type:\s*([0-9a-f]+)', output, re.IGNORECASE)
        if m:
            result['memory_type'] = m.group(1).lower()
        m = re.search(r'Capacity:\s*([0-9a-f]+)', output, re.IGNORECASE)
        if m:
            cap_byte = int(m.group(1), 16)
            # Capacity field : 18 = 2^24 bytes = 16 MB, 17 = 8 MB, etc.
            result['capacity'] = cap_byte
            result['size_kb'] = (1 << cap_byte) // 1024
        
        # Identification du vendor/modele a partir du Manufacturer ID
        # EF = Winbond, C2 = Macronix, 20 = Micron, 1F = Atmel, ...
        vendor_map = {
            'ef': 'Winbond',
            'c2': 'Macronix',
            '20': 'Micron',
            '1f': 'Atmel',
            '1c': 'EON',
            'bf': 'SST',
            '01': 'Spansion',
        }
        result['vendor'] = vendor_map.get(result.get('manufacturer_id', ''), 'Unknown')
        
        # Modele commun T470s : Winbond W25Q128.V
        # mfid=ef, mtype=40, cap=18 (16 Mo)
        if result.get('manufacturer_id') == 'ef' and result.get('memory_type', '').startswith('40'):
            cap = result.get('capacity', 0)
            if cap == 0x18:
                result['name'] = 'W25Q128.V'
            elif cap == 0x17:
                result['name'] = 'W25Q64.V'
            elif cap == 0x19:
                result['name'] = 'W25Q256.V'
            else:
                result['name'] = f'W25Q (cap=0x{cap:02x})'
        else:
            mfid = result.get('manufacturer_id', '??')
            mtype = result.get('memory_type', '??')
            cap = result.get('capacity', 0)
            result['name'] = f'{mfid}:{mtype}:0x{cap:02x}'
        
        if not result.get('size_kb'):
            # Fallback : detect_chip echoue
            raise Ch341progNotFoundError(
                f"Puce detectee partiellement mais capacite illisible.\n"
                f"ch341prog output:\n{output[-300:]}"
            )
        
        return result
    
    def read(
        self,
        output_path: str,
        on_log: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
    ) -> None:
        """
        Lit la puce SPI et sauvegarde dans output_path.
        
        Args:
            output_path: chemin du fichier .rom de destination
            on_log: callback(line) pour les logs
            on_progress: callback(percent, status) pour la barre de progression
        
        ch341prog appelle on_progress reellement en temps reel grace au
        fflush(stdout) apres chaque update. Pas de bufferisation comme flashrom.
        """
        cmd = [self.ch341prog_path, '-v', '-r', str(output_path)]
        
        def on_raw_progress(bytes_done, percent, elapsed, eta):
            # Adapter au format (percent, status)
            mb_done = bytes_done / (1024 * 1024)
            status = f"Lecture : {mb_done:.1f} Mo  •  ETA : {eta}s"
            if on_progress:
                on_progress(percent, status)
        
        returncode, output = self._run_with_progress(
            cmd, on_log=on_log, on_progress=on_raw_progress
        )
        
        if returncode != 0:
            output_lower = output.lower()
            if "couldn't open" in output_lower or "initialise libusb" in output_lower:
                raise Ch341progDriverError(
                    f"Driver libusb non configure.\n\n{output[-500:]}"
                )
            raise Ch341progError(
                f"Lecture echouee (code {returncode}) :\n{output[-500:]}"
            )
        
        if not Path(output_path).exists():
            raise Ch341progError(
                "Lecture terminee mais fichier manquant."
            )
    
    def write(
        self,
        input_path: str,
        on_log: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
    ) -> None:
        """
        Ecrit input_path sur la puce.
        
        ch341prog effectue : erase puis write (pas de verify automatique).
        On fait un verify manuel apres pour la securite.
        """
        if not Path(input_path).exists():
            raise Ch341progError(f"Fichier source introuvable : {input_path}")
        
        cmd = [self.ch341prog_path, '-v', '-w', str(input_path)]
        
        def on_raw_progress(bytes_done, percent, elapsed, eta):
            mb_done = bytes_done / (1024 * 1024)
            status = f"Ecriture : {mb_done:.1f} Mo  •  ETA : {eta}s"
            if on_progress:
                on_progress(percent, status)
        
        returncode, output = self._run_with_progress(
            cmd, on_log=on_log, on_progress=on_raw_progress
        )
        
        if returncode != 0:
            raise Ch341progError(
                f"Ecriture echouee (code {returncode}) :\n{output[-500:]}"
            )
    
    def verify(
        self,
        expected_path: str,
        on_log: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
    ) -> bool:
        """
        Lit la puce et compare au contenu de expected_path.
        ch341prog n'a pas de mode 'verify' natif, donc on relit dans un
        fichier temporaire et on compare.
        """
        if not Path(expected_path).exists():
            raise Ch341progError(f"Fichier de reference introuvable : {expected_path}")
        
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(suffix='.rom', delete=False)
        tmp.close()
        
        try:
            self.read(tmp.name, on_log=on_log, on_progress=on_progress)
            
            # Compare les contenus
            with open(expected_path, 'rb') as f:
                expected = f.read()
            with open(tmp.name, 'rb') as f:
                actual = f.read()
            
            return expected == actual
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ch341prog_wrapper.py <ch341prog.exe> [chip|read <file>|write <file>]")
        sys.exit(1)
    
    wrapper = Ch341progWrapper(sys.argv[1])
    cmd = sys.argv[2] if len(sys.argv) > 2 else 'chip'
    
    def log(line):
        print(f"  LOG: {line}")
    
    def progress(percent, status):
        print(f"  PROG: {percent:3d}%  {status}")
    
    if cmd == 'chip':
        info = wrapper.detect_chip(on_log=log)
        print(f"\nChip info: {info}")
    elif cmd == 'read':
        wrapper.read(sys.argv[3], on_log=log, on_progress=progress)
    elif cmd == 'write':
        wrapper.write(sys.argv[3], on_log=log, on_progress=progress)
