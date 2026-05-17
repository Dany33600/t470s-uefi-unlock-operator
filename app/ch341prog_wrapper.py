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

try:
    from i18n import t
except ImportError:
    # Fallback si i18n n'est pas dispo (usage standalone)
    def t(key, **kwargs):
        return key.format(**kwargs) if kwargs else key


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
                t('err.ch341a_not_found', output=output[-500:])
            )
        
        # Cas 2 : puce non trouvee
        if 'chip not found' in output_lower or 'missed in ch341a' in output_lower:
            raise Ch341progNotFoundError(
                t('err.chip_not_detected', output=output[-500:])
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
                t('err.chip_partial_detect', output=output[-300:])
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
        
        ch341prog appelle on_progress reellement en temps reel grace au
        fflush(stdout) apres chaque update.
        """
        cmd = [self.ch341prog_path, '-v', '-r', str(output_path)]
        
        def on_raw_progress(bytes_done, percent, elapsed, eta):
            # Adapter au format (percent, status), localisé
            mb_done = bytes_done / (1024 * 1024)
            status = t('workflow.read_status_mb', mb=mb_done, eta=eta)
            if on_progress:
                on_progress(percent, status)
        
        returncode, output = self._run_with_progress(
            cmd, on_log=on_log, on_progress=on_raw_progress
        )
        
        # Detection des erreurs dans la sortie meme si returncode == 0
        output_lower = output.lower()
        read_error_signatures = [
            'error while reading',
            'failed to read',
            "couldn't open",
            'initialise libusb',
        ]
        for sig in read_error_signatures:
            if sig in output_lower:
                if "couldn't open" in sig or 'initialise libusb' in sig:
                    raise Ch341progDriverError(
                        t('err.driver_not_configured', output=output[-500:])
                    )
                raise Ch341progError(
                    t('err.read_chip_failed',
                      code=f"{returncode} (detected: '{sig}')",
                      output=output[-600:])
                )
        
        if returncode != 0:
            output_lower = output.lower()
            if "couldn't open" in output_lower or "initialise libusb" in output_lower:
                raise Ch341progDriverError(
                    t('err.driver_not_configured', output=output[-500:])
                )
            raise Ch341progError(
                t('err.read_chip_failed', code=returncode, output=output[-500:])
            )
        
        if not Path(output_path).exists():
            raise Ch341progError(t('err.read_no_file'))
    
    def erase(
        self,
        on_log: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
    ) -> None:
        """
        Efface integralement la puce SPI (met tous les bits a 1 = 0xFF).
        
        Indispensable AVANT toute ecriture, car les puces flash NOR/NAND
        ne peuvent pas faire de transitions 0→1 sans erase prealable.
        ch341prog ne fait PAS l'erase automatique avant un -w, contrairement
        a NeoProgrammer ou flashrom.
        
        L'erase est rapide (~10-15s pour 16 Mo via la commande Chip Erase
        de la puce), mais ch341prog poll le status register toutes les
        secondes en affichant "." pour montrer l'avancee.
        """
        cmd = [self.ch341prog_path, '-v', '-e']
        
        # L'erase n'a pas de progression byte-par-byte, ch341prog affiche
        # juste des "." pendant l'attente. On simule une progression
        # indeterminee a base de timer.
        import time, threading
        
        progress_state = {'percent': 0, 'running': True}
        
        def progress_ticker():
            # Estimation : erase d'une puce 16 Mo prend ~15-20 sec
            # On fait monter la barre lineairement sur 20 sec, sans
            # depasser 95% tant que ch341prog n'a pas dit "Chip erase done".
            start = time.time()
            while progress_state['running']:
                elapsed = time.time() - start
                # Asymptote vers 95% en 20s
                pct = min(95, int(elapsed * 95 / 20))
                if pct != progress_state['percent']:
                    progress_state['percent'] = pct
                    if on_progress:
                        try:
                            status = t('workflow.erase_status', sec=int(elapsed))
                            on_progress(pct, status)
                        except Exception:
                            pass
                time.sleep(0.5)
        
        ticker_thread = threading.Thread(target=progress_ticker, daemon=True)
        ticker_thread.start()
        
        try:
            returncode, output = self._run_with_progress(
                cmd, on_log=on_log, on_progress=None
            )
        finally:
            progress_state['running'] = False
            ticker_thread.join(timeout=1)
        
        # Verifier que l'erase a reussi
        output_lower = output.lower()
        
        if "couldn't open" in output_lower or 'initialise libusb' in output_lower:
            raise Ch341progDriverError(
                t('err.driver_not_configured', output=output[-500:])
            )
        
        if 'chip not found' in output_lower:
            raise Ch341progNotFoundError(
                t('err.chip_not_detected', output=output[-500:])
            )
        
        if 'erase timeout' in output_lower or 'erase failed' in output_lower:
            raise Ch341progError(
                t('err.erase_failed', output=output[-500:])
            )
        
        # On veut voir "Chip erase done!" pour etre sur
        if 'chip erase done' not in output_lower:
            raise Ch341progError(
                t('err.erase_failed', output=output[-500:])
            )
        
        if on_progress:
            on_progress(100, t('workflow.erase_done_status'))
    
    def write(
        self,
        input_path: str,
        on_log: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
        skip_erase: bool = False,
    ) -> None:
        """
        Ecrit input_path sur la puce.
        
        IMPORTANT : ch341prog ne fait PAS d'erase automatique avant le
        write. Il faut le faire explicitement, sinon les bits a 1 dans
        l'ancien contenu qui doivent passer a 0 dans le nouveau echouent
        (erase met tout a 0xFF, et le write ne peut que faire 1→0).
        
        Workflow :
          1. erase (sauf si skip_erase=True)
          2. write
          3. ch341prog fait son verify natif et signale "Error while
             writing" si ca foire — on detecte ce signal.
        """
        if not Path(input_path).exists():
            raise Ch341progError(t('err.source_not_found', path=input_path))
        
        # ━━━ ETAPE 1/2 : ERASE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if not skip_erase:
            if on_log:
                on_log(t('workflow.erase_step_log'))
            self.erase(on_log=on_log, on_progress=on_progress)
        
        # ━━━ ETAPE 2/2 : WRITE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if on_log:
            on_log(t('workflow.write_step_log'))
        
        cmd = [self.ch341prog_path, '-v', '-w', str(input_path)]
        
        # Etat partage entre les callbacks pour suivre la phase courante :
        # 'write' (par defaut) ou 'verify' (apres "Write ok! Try to verify").
        # ch341prog fait son verify natif juste apres le write, dans le meme
        # process, et n'affiche pas de message distinct entre les deux. On
        # detecte le passage en surveillant la ligne "Write ok!".
        phase_state = {'phase': 'write'}
        
        def on_log_with_phase_detect(line):
            line_lower = line.lower()
            # Detection du passage write -> verify (phase native ch341prog).
            # On le signale UNE seule fois (le premier match).
            if phase_state['phase'] == 'write' and (
                'write ok' in line_lower or 'try to verify' in line_lower
            ):
                phase_state['phase'] = 'verify'
                if on_log:
                    on_log(t('workflow.verify_native_log'))
            # Forwarde la ligne brute au callback utilisateur
            if on_log:
                on_log(line)
        
        def on_raw_progress(bytes_done, percent, elapsed, eta):
            mb_done = bytes_done / (1024 * 1024)
            # Le label depend de la phase courante
            if phase_state['phase'] == 'verify':
                status = t('workflow.verify_native_status', mb=mb_done, eta=eta)
            else:
                status = t('workflow.write_status_mb', mb=mb_done, eta=eta)
            if on_progress:
                on_progress(percent, status)
        
        returncode, output = self._run_with_progress(
            cmd, on_log=on_log_with_phase_detect, on_progress=on_raw_progress
        )
        
        # Detection des erreurs dans la sortie meme si returncode == 0.
        # ch341prog fait un verify natif APRES le write, et peut signaler
        # "Error while writing" tout en se terminant avec un code 0.
        output_lower = output.lower()
        error_signatures = [
            'error while writing',
            'may be it need to be erased',
            'failed to write',
            'verification failed',
            'verification error',
            'write failed',
            "couldn't open",
            'initialise libusb',
        ]
        for sig in error_signatures:
            if sig in output_lower:
                raise Ch341progError(
                    t('err.write_chip_failed',
                      code=f"{returncode} (detected: '{sig}')",
                      output=output[-600:])
                )
        
        if returncode != 0:
            raise Ch341progError(
                t('err.write_chip_failed', code=returncode, output=output[-500:])
            )
    
    def verify(
        self,
        expected_path: str,
        on_log: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
    ) -> bool:
        """
        Lit la puce et compare au contenu de expected_path.
        """
        if not Path(expected_path).exists():
            raise Ch341progError(t('err.ref_not_found', path=expected_path))
        
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
