"""
Wrapper Python pour flashrom + CH341A sous Windows.
"""
import subprocess
import re
from pathlib import Path
from typing import Callable, Optional


class FlashromError(Exception):
    pass


class ChipNotDetectedError(FlashromError):
    pass


class DriverNotInstalledError(FlashromError):
    """Le CH341A est branche mais le driver libusb (WinUSB) n'est pas
    installe. Il faut lancer Zadig pour remplacer le driver CH341PAR
    natif par WinUSB."""
    pass


class WriteVerifyError(FlashromError):
    pass


class FlashromWrapper:
    def __init__(self, flashrom_path: str = 'flashrom.exe',
                 chip_name: Optional[str] = None):
        self.flashrom_path = flashrom_path
        self.chip_name = chip_name
    
    def _build_cmd(self, *args) -> list:
        cmd = [self.flashrom_path, '-p', 'ch341a_spi', '--progress']
        if self.chip_name:
            cmd.extend(['-c', self.chip_name])
        cmd.extend(args)
        return cmd
    
    def _run(self, cmd: list, on_progress: Optional[Callable[[str], None]] = None) -> tuple:
        """
        Lance flashrom et stream stdout/stderr. flashrom avec --progress
        utilise \\r (carriage return) pour rafraichir la ligne de
        progression sur la meme position du terminal, donc on lit
        caractere par caractere et on traite \\r comme un saut de ligne
        pour les callbacks.
        """
        flags = 0
        if hasattr(subprocess, 'CREATE_NO_WINDOW'):
            flags = subprocess.CREATE_NO_WINDOW
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,  # non-bufferise pour temps reel
            creationflags=flags,
        )
        
        output_lines = []
        current_line = bytearray()
        last_callback_line = ''
        
        while True:
            ch = process.stdout.read(1)
            if not ch:
                break
            
            if ch in (b'\n', b'\r'):
                # Fin de ligne (soit \n soit \r de rafraichissement)
                if current_line:
                    try:
                        line = current_line.decode('utf-8', errors='replace').rstrip()
                    except Exception:
                        line = current_line.decode('latin-1', errors='replace').rstrip()
                    
                    if line and line != last_callback_line:
                        output_lines.append(line)
                        if on_progress:
                            try:
                                on_progress(line)
                            except Exception:
                                pass
                        last_callback_line = line
                    
                    current_line = bytearray()
            else:
                current_line.extend(ch)
        
        # Derniere ligne (si pas terminee par \n)
        if current_line:
            try:
                line = current_line.decode('utf-8', errors='replace').rstrip()
            except Exception:
                line = current_line.decode('latin-1', errors='replace').rstrip()
            if line:
                output_lines.append(line)
                if on_progress:
                    try:
                        on_progress(line)
                    except Exception:
                        pass
        
        process.wait()
        return process.returncode, '\n'.join(output_lines)
    
    def detect_chip(self, on_progress: Optional[Callable] = None) -> dict:
        cmd = self._build_cmd()
        returncode, output = self._run(cmd, on_progress)
        
        match = re.search(
            r'Found\s+(\S+)\s+flash chip\s+"([^"]+)"\s+\((\d+)\s*kB',
            output
        )
        if not match:
            output_lower = output.lower()
            
            # Cas 1 : driver libusb non installe (CH341A vu en USB mais
            # pas accessible par flashrom car driver CH341PAR au lieu de WinUSB)
            # Signature typique : "Couldn't open device 1a86:5512"
            if ("couldn't open device" in output_lower or 
                "could not open device" in output_lower or
                "1a86:5512" in output_lower or
                ("programmer initialization failed" in output_lower and 
                 "ch341a" in output_lower)):
                raise DriverNotInstalledError(
                    "Le CH341A est branche mais le driver libusb (WinUSB) "
                    "n'est pas installe.\n\n"
                    "Il faut remplacer le driver CH341PAR par WinUSB via Zadig.\n\n"
                    f"flashrom output:\n{output[-500:]}"
                )
            
            # Cas 2 : CH341A non vu du tout (pas branche ou erreur USB)
            if 'ch341a' not in output_lower:
                raise ChipNotDetectedError(
                    "CH341A non detecte.\n"
                    "Verifie :\n"
                    "- Le CH341A est branche en USB\n"
                    "- Aucun autre logiciel n'utilise le CH341A actuellement\n\n"
                    f"flashrom output:\n{output[-500:]}"
                )
            
            # Cas 3 : CH341A OK mais pas de puce SPI trouvee
            raise ChipNotDetectedError(
                "CH341A detecte mais aucune puce SPI trouvee.\n"
                "Verifie l'orientation du clip SOIC-8 "
                "(ligne rouge ↔ point sur la puce).\n\n"
                f"flashrom output:\n{output[-500:]}"
            )
        
        return {
            'vendor': match.group(1),
            'name': match.group(2),
            'size_kb': int(match.group(3)),
        }
    
    def read(self, output_path: str, on_progress: Optional[Callable] = None,
             on_size_progress: Optional[Callable] = None,
             expected_size_kb: int = 16384) -> None:
        """
        Lit la puce SPI et sauvegarde dans output_path.
        
        Args:
            output_path: chemin du fichier .rom de destination
            on_progress: callback ligne par ligne (logs)
            on_size_progress: callback(percent, status) pour la progression
                            basee sur la taille du fichier en cours d'ecriture
            expected_size_kb: taille attendue de la puce (16384 = 16 Mo)
        """
        cmd = self._build_cmd('-r', str(output_path))
        output_file = Path(output_path)
        expected_bytes = expected_size_kb * 1024
        
        # Lancer flashrom dans un thread, surveiller la taille du fichier
        # dans le thread principal
        import threading
        import time
        
        flags = 0
        if hasattr(subprocess, 'CREATE_NO_WINDOW'):
            flags = subprocess.CREATE_NO_WINDOW
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=flags,
        )
        
        # Thread qui lit la sortie texte de flashrom
        output_lines = []
        output_lock = threading.Lock()
        
        def reader_thread():
            current_line = bytearray()
            last_line = ''
            while True:
                ch = process.stdout.read(1)
                if not ch:
                    break
                if ch in (b'\n', b'\r'):
                    if current_line:
                        line = current_line.decode('utf-8', errors='replace').rstrip()
                        if line and line != last_line:
                            with output_lock:
                                output_lines.append(line)
                            if on_progress:
                                try:
                                    on_progress(line)
                                except Exception:
                                    pass
                            last_line = line
                        current_line = bytearray()
                else:
                    current_line.extend(ch)
            if current_line:
                line = current_line.decode('utf-8', errors='replace').rstrip()
                if line:
                    with output_lock:
                        output_lines.append(line)
                    if on_progress:
                        try:
                            on_progress(line)
                        except Exception:
                            pass
        
        t = threading.Thread(target=reader_thread, daemon=True)
        t.start()
        
        # Boucle de monitoring de la taille du fichier
        last_size = 0
        last_change_time = time.time()
        
        while process.poll() is None:
            if output_file.exists():
                try:
                    current_size = output_file.stat().st_size
                    if current_size != last_size:
                        last_change_time = time.time()
                        last_size = current_size
                    
                    if expected_bytes > 0:
                        percent = int(current_size * 100 / expected_bytes)
                        percent = min(99, percent)  # 100% qu'a la fin
                        
                        mb_done = current_size / 1024 / 1024
                        mb_total = expected_bytes / 1024 / 1024
                        status = f"Lecture : {mb_done:.1f} / {mb_total:.1f} Mo"
                        
                        if on_size_progress:
                            try:
                                on_size_progress(percent, status)
                            except Exception:
                                pass
                except OSError:
                    pass
            
            time.sleep(0.5)
        
        # Attendre la fin du reader thread
        t.join(timeout=2)
        
        # 100% final
        if on_size_progress:
            try:
                on_size_progress(100, "Lecture terminee")
            except Exception:
                pass
        
        returncode = process.returncode
        full_output = '\n'.join(output_lines)
        
        if returncode != 0:
            raise FlashromError(f"Lecture échouée :\n{full_output[-500:]}")
        if not output_file.exists():
            raise FlashromError("Lecture terminée mais fichier manquant.")
    
    def write(self, input_path: str, on_progress: Optional[Callable] = None,
              on_size_progress: Optional[Callable] = None) -> None:
        """
        Ecrit input_path sur la puce. flashrom fait :
          1. Read (lecture initiale pour comparaison) - ~2 min
          2. Erase + Write - ~1 min
          3. Verify (relecture pour confirmation) - ~2 min
        
        On estime la progression sur 5 min total.
        """
        if not Path(input_path).exists():
            raise FlashromError(f"Fichier source introuvable : {input_path}")
        
        cmd = self._build_cmd('-w', str(input_path))
        
        import threading
        import time
        
        flags = 0
        if hasattr(subprocess, 'CREATE_NO_WINDOW'):
            flags = subprocess.CREATE_NO_WINDOW
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=flags,
        )
        
        output_lines = []
        output_lock = threading.Lock()
        current_phase = {'phase': 'init', 'percent': 0}
        
        def reader_thread():
            current_line = bytearray()
            last_line = ''
            while True:
                ch = process.stdout.read(1)
                if not ch:
                    break
                if ch in (b'\n', b'\r'):
                    if current_line:
                        line = current_line.decode('utf-8', errors='replace').rstrip()
                        if line and line != last_line:
                            with output_lock:
                                output_lines.append(line)
                            if on_progress:
                                try:
                                    on_progress(line)
                                except Exception:
                                    pass
                            last_line = line
                            
                            # Detecter les phases pour estimation
                            line_lower = line.lower()
                            if 'reading old flash chip' in line_lower:
                                current_phase['phase'] = 'reading'
                            elif 'erasing and writing flash chip' in line_lower:
                                current_phase['phase'] = 'writing'
                            elif 'verifying flash' in line_lower:
                                current_phase['phase'] = 'verifying'
                            elif 'verified' in line_lower:
                                current_phase['phase'] = 'done'
                        current_line = bytearray()
                else:
                    current_line.extend(ch)
            if current_line:
                line = current_line.decode('utf-8', errors='replace').rstrip()
                if line:
                    with output_lock:
                        output_lines.append(line)
                    if on_progress:
                        try:
                            on_progress(line)
                        except Exception:
                            pass
        
        t = threading.Thread(target=reader_thread, daemon=True)
        t.start()
        
        # Boucle de monitoring : progression basee sur le temps + phase
        start_time = time.time()
        # Estimation : 4-5 min pour une puce 16 Mo
        # Phases approximatives :
        #   reading initial : 0-35% (~2 min)
        #   erasing+writing : 35-65% (~1 min)
        #   verifying       : 65-99% (~2 min)
        ESTIMATED_TOTAL_SEC = 280  # 4 min 40s
        
        while process.poll() is None:
            elapsed = time.time() - start_time
            
            # Progression basee sur phase si detectee, sinon sur le temps
            phase = current_phase['phase']
            if phase == 'reading':
                # 0-35% pendant la phase reading
                phase_percent = min(35, int(elapsed / ESTIMATED_TOTAL_SEC * 100))
                status = "Lecture initiale (verification)"
            elif phase == 'writing':
                # 35-65%
                phase_percent = min(65, max(35, int(elapsed / ESTIMATED_TOTAL_SEC * 100)))
                status = "Effacement + ecriture"
            elif phase == 'verifying':
                # 65-99%
                phase_percent = min(99, max(65, int(elapsed / ESTIMATED_TOTAL_SEC * 100)))
                status = "Verification finale"
            elif phase == 'done':
                phase_percent = 100
                status = "VERIFIED"
            else:
                # Pas encore de phase detectee : estimation temporelle pure
                phase_percent = min(30, int(elapsed / ESTIMATED_TOTAL_SEC * 100))
                status = "Initialisation"
            
            if on_size_progress:
                try:
                    on_size_progress(phase_percent, status)
                except Exception:
                    pass
            
            time.sleep(1)
        
        t.join(timeout=2)
        
        if on_size_progress:
            try:
                on_size_progress(100, "Termine")
            except Exception:
                pass
        
        returncode = process.returncode
        full_output = '\n'.join(output_lines)
        
        if 'VERIFIED' not in full_output:
            raise WriteVerifyError(
                f"Écriture terminée sans VERIFIED.\n\n{full_output[-500:]}"
            )
        if returncode != 0:
            raise FlashromError(f"Écriture échouée (code {returncode}) :\n{full_output[-500:]}")
    
    def verify(self, expected_path: str, on_progress: Optional[Callable] = None) -> bool:
        cmd = self._build_cmd('-v', str(expected_path))
        returncode, output = self._run(cmd, on_progress)
        return returncode == 0 and 'VERIFIED' in output
