"""
T470s Operator — Installeur
============================
Detecte ce qui manque, telecharge et installe ce qu'il faut,
guide l'utilisateur pour les drivers Zadig.

Composants geres :
  - flashrom.exe (binaire Windows x64 avec support ch341a_spi)
  - Zadig.exe (pour installer le driver libusb du CH341A)
  - lenovo_autopatcher/ (extrait du zip embarque ou telecharge)
  - Structure de dossiers (dumps, reports)
  - Dialogue interactif pour l'install du driver libusb

Si tout est deja OK, l'installeur termine immediatement.
"""
import os
import sys
import json
import urllib.request
import urllib.error
import zipfile
import shutil
import subprocess
import hashlib
from pathlib import Path
from tkinter import Tk, Label, Button, Frame, Toplevel, messagebox
from tkinter import ttk
import tkinter as tk


# ════ CONFIGURATION DES TELECHARGEMENTS ════════════════════════
# flashrom : telechargement direct du .exe depuis le repo
# (le repo therealdreg contient les binaires versionnes dans son arborescence)
DOWNLOADS = {
    'flashrom': {
        # On telecharge l'archive du tag (~5 Mo) qui contient flashrom.exe
        # + libusb-1.0.dll + libwinpthread-1.dll + libftdi1.dll
        # Necessaire car les .exe MinGW ne sont pas statiques.
        'url': 'https://github.com/therealdreg/flashrom_build_windows_x64/archive/refs/tags/1.4.zip',
        'output_filename': 'flashrom_pack.zip',
        'is_zip': True,
        'description': 'flashrom 1.4 (Windows x64, support CH341A)',
    },
    'zadig': {
        'url': 'https://github.com/pbatard/libwdi/releases/download/v1.5.1/zadig-2.9.exe',
        'output_filename': 'zadig.exe',
        'is_zip': False,
        'description': 'Zadig 2.9 (installeur de driver libusb)',
    },
}

# Chemins (relatifs au root du projet)
ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / 'tools'
APP_DIR = ROOT / 'app'
RESOURCES = ROOT / 'resources'
DUMPS = ROOT / 'dumps'
REPORTS = ROOT / 'reports'
LOGS = ROOT / 'logs'
CONFIG_FILE = ROOT / 'config.json'

# Couleurs (dark theme)
C = {
    'bg':       '#1a1b26',
    'bg_alt':   '#24283b',
    'bg_widget':'#2f334d',
    'fg':       '#c0caf5',
    'fg_dim':   '#a9b1d6',
    'accent':   '#7aa2f7',
    'success':  '#9ece6a',
    'warning':  '#e0af68',
    'error':    '#f7768e',
    'border':   '#414868',
}


# ════ Mini i18n pour l'installeur ══════════════════════════════
INSTALLER_TRANSLATIONS = {
    'fr': {
        'title': 'T470s Operator — Installeur',
        'header': '🔧  Installation des composants',
        'subtitle': 'Vérification et téléchargement de ce qui manque',
        'step_folders': '📁 Structure de dossiers',
        'step_flashrom': '🔥 flashrom.exe (programmateur)',
        'step_ch341prog': '⚡ ch341prog.exe (progression temps réel)',
        'step_autopatcher': '⚙️ Autopatcher Lenovo',
        'step_zadig': '🔌 Zadig (driver libusb)',
        'step_driver': '🚗 Driver CH341A (libusb)',
        'detail.creating': 'création...',
        'detail.already_present': 'déjà présent',
        'detail.downloading': 'téléchargement...',
        'detail.extracting': 'extraction...',
        'detail.up_to_date': 'à jour',
        'detail.copying': 'copie depuis resources...',
        'detail.sources_missing': 'sources manquants',
        'detail.copy_failed': 'copie échouée',
        'detail.dl_failed': 'échec téléchargement',
        'detail.extract_failed': 'échec extraction',
        'detail.invalid_file': 'fichier invalide',
        'detail.zip_missing': 'zip manquant',
        'detail.extracted': 'extrait',
        'detail.verifying': 'vérification...',
        'detail.libusb_ok': 'libusb détecté',
        'detail.manual_setup': 'configuration manuelle requise',
        'detail.reverifying': 're-vérification...',
        'detail.configured': 'configuré',
        'detail.verify_failed': 'vérification échouée',
        'detail.manual_todo': 'à configurer manuellement',
        'btn.install': '▶  Installer',
        'btn.installing': 'Installation en cours...',
        'btn.retry': '▶  Réessayer',
        'btn.finish': '✅  Terminer',
        'err.title': "Erreur d'installation",
        'err.dl_impossible': 'Téléchargement de {tool} impossible :\n{err}',
        'autopatcher.msg': (
            "L'autopatcher Lenovo n'est pas embarqué dans l'installeur.\n\n"
            "Télécharge 'lenovo_autopatcher_0.2.zip' depuis :\n"
            "https://github.com/lilianalillyy/t470s-uefi-unlock\n\n"
            "Place-le dans :\n{path}\n\n"
            "Puis relance l'installation."
        ),
        'autopatcher.title': 'Autopatcher manquant',
        'ch341prog.title': 'ch341prog manquant',
        'ch341prog.msg': (
            "Les binaires ch341prog ne sont pas embarqués.\n\n"
            "Fichiers attendus :\n  {exe}\n  {dll}\n\n"
            "Réinstalle l'application à partir du zip d'origine."
        ),
        'finalize.title': 'Installation terminée',
        'finalize.msg': (
            "✅ Tous les composants sont installés.\n\n"
            "Lancement de l'application principale..."
        ),
        'finalize.btn_ok': "✅  Tout est prêt — Lancer l'app",
        'finalize.btn_warn': "✅  Lancer l'app (driver à configurer)",
        'finalize.btn_failed': '⚠ Échec : {failed}',
        'finalize.incomplete_title': 'Installation incomplète',
        'finalize.incomplete_msg': (
            'Composants critiques manquants : {failed}\n\n'
            'Résolvez puis relancez.'
        ),
    },
    'en': {
        'title': 'T470s Operator — Installer',
        'header': '🔧  Component installation',
        'subtitle': "Verifying and downloading what's missing",
        'step_folders': '📁 Folder structure',
        'step_flashrom': '🔥 flashrom.exe (programmer)',
        'step_ch341prog': '⚡ ch341prog.exe (real-time progress)',
        'step_autopatcher': '⚙️ Lenovo Autopatcher',
        'step_zadig': '🔌 Zadig (libusb driver)',
        'step_driver': '🚗 CH341A driver (libusb)',
        'detail.creating': 'creating...',
        'detail.already_present': 'already present',
        'detail.downloading': 'downloading...',
        'detail.extracting': 'extracting...',
        'detail.up_to_date': 'up to date',
        'detail.copying': 'copying from resources...',
        'detail.sources_missing': 'sources missing',
        'detail.copy_failed': 'copy failed',
        'detail.dl_failed': 'download failed',
        'detail.extract_failed': 'extraction failed',
        'detail.invalid_file': 'invalid file',
        'detail.zip_missing': 'zip missing',
        'detail.extracted': 'extracted',
        'detail.verifying': 'verifying...',
        'detail.libusb_ok': 'libusb detected',
        'detail.manual_setup': 'manual setup required',
        'detail.reverifying': 're-verifying...',
        'detail.configured': 'configured',
        'detail.verify_failed': 'verification failed',
        'detail.manual_todo': 'manual setup needed',
        'btn.install': '▶  Install',
        'btn.installing': 'Installing...',
        'btn.retry': '▶  Retry',
        'btn.finish': '✅  Finish',
        'err.title': 'Installation error',
        'err.dl_impossible': 'Cannot download {tool}:\n{err}',
        'autopatcher.msg': (
            "The Lenovo autopatcher is not embedded in the installer.\n\n"
            "Download 'lenovo_autopatcher_0.2.zip' from:\n"
            "https://github.com/lilianalillyy/t470s-uefi-unlock\n\n"
            "Place it in:\n{path}\n\n"
            "Then re-run the installer."
        ),
        'autopatcher.title': 'Autopatcher missing',
        'ch341prog.title': 'ch341prog missing',
        'ch341prog.msg': (
            "The ch341prog binaries are not embedded.\n\n"
            "Expected files:\n  {exe}\n  {dll}\n\n"
            "Reinstall the application from the original zip."
        ),
        'finalize.title': 'Installation complete',
        'finalize.msg': (
            "✅ All components installed.\n\n"
            "Launching main application..."
        ),
        'finalize.btn_ok': '✅  Ready — Launch app',
        'finalize.btn_warn': '✅  Launch app (driver setup needed)',
        'finalize.btn_failed': '⚠ Failed: {failed}',
        'finalize.incomplete_title': 'Incomplete installation',
        'finalize.incomplete_msg': (
            'Critical components missing: {failed}\n\n'
            'Fix and retry.'
        ),
    },
}


def _load_installer_lang():
    """Charge la langue depuis config.json ou les args. Defaut: fr."""
    # 1) args
    for arg in sys.argv[1:]:
        if arg.startswith('--lang='):
            lang = arg.split('=', 1)[1].strip().lower()
            if lang in INSTALLER_TRANSLATIONS:
                return lang
    # 2) config
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        lang = cfg.get('language', 'fr')
        if lang in INSTALLER_TRANSLATIONS:
            return lang
    except (OSError, json.JSONDecodeError):
        pass
    return 'fr'


_LANG = _load_installer_lang()


def L(key, **kwargs):
    """Traduit une clé pour l'installeur."""
    txt = INSTALLER_TRANSLATIONS.get(_LANG, {}).get(key)
    if txt is None:
        txt = INSTALLER_TRANSLATIONS['fr'].get(key, key)
    if kwargs:
        try:
            return txt.format(**kwargs)
        except (KeyError, IndexError):
            return txt
    return txt


# ════ UTILITAIRES ═══════════════════════════════════════════════
def download_file(url: str, dest: Path, progress_cb=None) -> None:
    """
    Telecharge un fichier. Strategie en cascade pour eviter les
    problemes SSL sur Windows (notamment dans Sandbox Windows ou
    nouvelles installs ou les certs CA ne sont pas dispo).
    
    1. Essai via PowerShell Invoke-WebRequest (utilise le store
       de certificats Windows, generalement OK)
    2. Fallback urllib avec verification SSL desactivee
       (acceptable car on telecharge uniquement depuis GitHub
       officiel et python.org)
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    # ─── Methode 1 : PowerShell ─────────────────────────────────
    try:
        if progress_cb:
            progress_cb(0, 0, 0)
        
        ps_cmd = (
            f"$ProgressPreference = 'SilentlyContinue'; "
            f"[Net.ServicePointManager]::SecurityProtocol = "
            f"[Net.SecurityProtocolType]::Tls12; "
            f"Invoke-WebRequest -Uri '{url}' -OutFile '{dest}' "
            f"-UseBasicParsing -ErrorAction Stop"
        )
        
        result = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
             '-Command', ps_cmd],
            capture_output=True, text=True, timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
        
        if result.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            if progress_cb:
                size = dest.stat().st_size
                progress_cb(100, size, size)
            return
        
        # Si PowerShell echoue, on tente urllib
        ps_error = result.stderr.strip() or result.stdout.strip()
    except subprocess.TimeoutExpired:
        ps_error = "PowerShell timeout (180s)"
    except Exception as e:
        ps_error = f"PowerShell: {e}"
    
    # ─── Methode 2 : urllib sans verif SSL ──────────────────────
    # On reessaie avec urllib en desactivant la verif SSL
    # (car le probleme initial vient typiquement d'un manque de
    # certificats CA dans l'env Python).
    import ssl
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    if dest.exists():
        dest.unlink()
    
    try:
        req = urllib.request.Request(
            url, headers={'User-Agent': 'Mozilla/5.0 (T470s-Operator)'}
        )
        
        with urllib.request.urlopen(req, timeout=60, context=ctx) as response:
            total = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            chunk_size = 8192
            
            with open(dest, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total > 0:
                        pct = int(downloaded * 100 / total)
                        progress_cb(pct, downloaded, total)
    except Exception as urllib_error:
        raise Exception(
            f"Telechargement impossible.\n"
            f"PowerShell: {ps_error}\n"
            f"urllib: {urllib_error}"
        )


def extract_zip(zip_path: Path, target_dir: Path, target_filename: str = None) -> Path:
    """
    Extrait un zip. Si target_filename est fourni, copie/extrait juste ce fichier
    a la racine de target_dir. Sinon extrait tout.
    Retourne le chemin du fichier cible (ou target_dir).
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        if target_filename:
            # Chercher le fichier dans le zip (peut etre dans un sous-dossier)
            for member in zf.namelist():
                if Path(member).name.lower() == target_filename.lower():
                    # Extraire en gardant juste le nom de fichier
                    with zf.open(member) as src:
                        out_path = target_dir / target_filename
                        with open(out_path, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                    return out_path
            raise FileNotFoundError(f"{target_filename} introuvable dans le zip")
        else:
            zf.extractall(target_dir)
            return target_dir


def check_libusb_driver() -> bool:
    """
    Tente de detecter si le driver libusb est installe pour le CH341A.
    Strategie : on lance flashrom.exe -p ch341a_spi et on regarde si
    l'erreur est "device not found" (driver OK mais pas branche) vs
    "no permission" / "no driver" (driver KO).
    
    Retourne True si le driver semble OK, False sinon.
    Si flashrom.exe n'existe pas encore, retourne None.
    """
    flashrom = TOOLS / 'flashrom.exe'
    if not flashrom.exists():
        return None
    
    try:
        result = subprocess.run(
            [str(flashrom), '-p', 'ch341a_spi'],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
        output = (result.stdout + result.stderr).lower()
        
        # Driver OK = on a au moins une trace que le programmateur s'initialise
        if 'initializing ch341a' in output or 'ch341a' in output:
            # Si on a "device not found", le driver est OK mais le CH341A
            # n'est pas branche ou pas vu. C'est OK.
            return True
        if 'no device' in output and 'permission' not in output:
            return True
        # Erreur generique = on suppose que c'est OK et on laisse l'app
        # gerer le cas precis lors du premier appel reel
        return True
    except Exception:
        return False


# ════ FENETRE PRINCIPALE DE L'INSTALLEUR ════════════════════════
class InstallerUI:
    def __init__(self, root: Tk):
        self.root = root
        self.tasks_done = []
        self.tasks_failed = []
        self._build_ui()
    
    def _build_ui(self):
        self.root.title(L('title'))
        self.root.geometry("720x520")
        self.root.configure(bg=C['bg'])
        self.root.resizable(False, False)
        
        # Header
        header = Frame(self.root, bg=C['bg_alt'], height=80)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        Label(header, text=L('header'),
              font=('Segoe UI', 18, 'bold'),
              bg=C['bg_alt'], fg=C['accent']
              ).pack(pady=(15, 0))
        Label(header, text=L('subtitle'),
              font=('Segoe UI', 10),
              bg=C['bg_alt'], fg=C['fg_dim']
              ).pack()
        
        # Zone d'etapes
        self.content = Frame(self.root, bg=C['bg'])
        self.content.pack(fill='both', expand=True, padx=30, pady=20)
        
        # Labels des etapes (mis a jour dynamiquement)
        self.step_labels = {}
        steps = [
            ('folders', L('step_folders')),
            ('flashrom', L('step_flashrom')),
            ('ch341prog', L('step_ch341prog')),
            ('autopatcher', L('step_autopatcher')),
            ('zadig', L('step_zadig')),
            ('driver', L('step_driver')),
        ]
        
        for key, text in steps:
            row = Frame(self.content, bg=C['bg'])
            row.pack(fill='x', pady=6)
            
            status = Label(row, text='⏳', font=('Segoe UI', 14),
                          bg=C['bg'], fg=C['warning'], width=3)
            status.pack(side='left')
            
            label = Label(row, text=text, font=('Segoe UI', 11),
                         bg=C['bg'], fg=C['fg'], anchor='w')
            label.pack(side='left', fill='x', expand=True)
            
            detail = Label(row, text='', font=('Segoe UI', 9),
                          bg=C['bg'], fg=C['fg_dim'])
            detail.pack(side='right')
            
            self.step_labels[key] = {'status': status, 'detail': detail}
        
        # Barre de progression
        self.progress_frame = Frame(self.content, bg=C['bg'])
        self.progress_frame.pack(fill='x', pady=(20, 10))
        
        self.progress_label = Label(self.progress_frame, text='',
                                    font=('Segoe UI', 9),
                                    bg=C['bg'], fg=C['fg_dim'])
        self.progress_label.pack(anchor='w')
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Dark.Horizontal.TProgressbar',
                       background=C['accent'], troughcolor=C['bg_widget'],
                       bordercolor=C['border'])
        
        self.progress = ttk.Progressbar(
            self.progress_frame, mode='determinate',
            style='Dark.Horizontal.TProgressbar', length=600
        )
        self.progress.pack(fill='x', pady=4)
        
        # Bouton
        btn_frame = Frame(self.root, bg=C['bg'])
        btn_frame.pack(side='bottom', fill='x', padx=30, pady=20)
        
        self.action_btn = Button(
            btn_frame, text=L('btn.install'),
            command=self.start_install,
            font=('Segoe UI', 11, 'bold'),
            bg=C['accent'], fg=C['bg'],
            relief='flat', cursor='hand2', pady=10, borderwidth=0,
            activebackground=C['border'], activeforeground=C['fg'],
        )
        self.action_btn.pack(fill='x')
    
    def _set_step(self, key: str, status: str, detail: str = '', color: str = None):
        """status: 'todo', 'doing', 'ok', 'fail'"""
        icons = {'todo': '⏳', 'doing': '⚙', 'ok': '✅', 'fail': '❌'}
        colors = {
            'todo': C['warning'], 'doing': C['accent'],
            'ok': C['success'], 'fail': C['error'],
        }
        self.step_labels[key]['status'].config(
            text=icons.get(status, '?'),
            fg=color or colors.get(status, C['fg'])
        )
        self.step_labels[key]['detail'].config(text=detail)
        self.root.update_idletasks()
    
    def _set_progress(self, text: str, pct: int = 0):
        self.progress_label.config(text=text)
        self.progress['value'] = pct
        self.root.update_idletasks()
    
    # ─── INSTALLATION ────────────────────────────────────────────
    def start_install(self):
        self.action_btn.config(state='disabled', text=L('btn.installing'))
        self.root.after(100, self.run_install)
    
    def run_install(self):
        try:
            self.step_folders()
            self.step_flashrom()
            self.step_ch341prog()
            self.step_autopatcher()
            self.step_zadig()
            self.step_driver()
            self.finalize()
        except Exception as e:
            messagebox.showerror(L('err.title'), str(e))
            self.action_btn.config(state='normal',
                                    text=L('btn.retry'),
                                    command=self.start_install)
    
    def step_folders(self):
        self._set_step('folders', 'doing', L('detail.creating'))
        for d in (TOOLS, APP_DIR, RESOURCES, DUMPS, REPORTS, LOGS):
            d.mkdir(parents=True, exist_ok=True)
        self._set_step('folders', 'ok', f'{ROOT.name}/')
        self.tasks_done.append('folders')
    
    def step_flashrom(self):
        flashrom = TOOLS / 'flashrom.exe'
        if flashrom.exists():
            self._set_step('flashrom', 'ok', L('detail.already_present'))
            self.tasks_done.append('flashrom')
            return
        
        self._set_step('flashrom', 'doing', L('detail.downloading'))
        
        info = DOWNLOADS['flashrom']
        zip_path = TOOLS / 'flashrom_pack.zip'
        
        def progress_cb(pct, downloaded, total):
            mb = downloaded / 1024 / 1024
            total_mb = total / 1024 / 1024 if total > 0 else 0
            self._set_progress(
                f"flashrom : {mb:.1f} / {total_mb:.1f} Mo", pct
            )
        
        try:
            download_file(info['url'], zip_path, progress_cb)
        except Exception as e:
            self._set_step('flashrom', 'fail', L('detail.dl_failed'))
            raise Exception(L('err.dl_impossible', tool='flashrom', err=e))
        
        self._set_progress("flashrom : extraction...", 100)
        
        # Extraction du zip + copie de flashrom.exe et de toutes les DLL
        # vers TOOLS/ (a plat). Les fichiers sont dans un sous-dossier
        # comme flashrom_build_windows_x64-1.4/ dans le zip.
        try:
            # Fichiers a extraire (le .exe et toutes les DLL adjacentes)
            wanted_files = [
                'flashrom.exe',
                'libusb-1.0.dll',
                'libwinpthread-1.dll',
                'libftdi1.dll',
                'zlib1.dll',
                'libgcc_s_seh-1.dll',
                'libstdc++-6.dll',
            ]
            
            extracted = []
            
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for member in zf.namelist():
                    # On regarde seulement les fichiers a la racine du
                    # sous-dossier principal (pas dans x32_flashrom/)
                    parts = member.replace('\\', '/').split('/')
                    
                    # On ignore les fichiers dans des sous-dossiers
                    # (sauf le 1er niveau qui est le nom du repo)
                    if len(parts) != 2:
                        continue
                    
                    filename = parts[1].lower()
                    
                    for wanted in wanted_files:
                        if filename == wanted.lower():
                            target = TOOLS / wanted
                            with zf.open(member) as src, open(target, 'wb') as dst:
                                shutil.copyfileobj(src, dst)
                            extracted.append(wanted)
                            break
        except Exception as e:
            self._set_step('flashrom', 'fail', L('detail.extract_failed'))
            raise Exception(f"Extraction de flashrom impossible :\n{e}")
        finally:
            if zip_path.exists():
                zip_path.unlink()
        
        if not flashrom.exists() or flashrom.stat().st_size < 100000:
            self._set_step('flashrom', 'fail', L('detail.invalid_file'))
            raise Exception(
                f"flashrom.exe non extrait correctement.\n"
                f"Fichiers extraits : {extracted}"
            )
        
        detail = f'{flashrom.stat().st_size // 1024} KB + {len(extracted)-1} DLL'
        self._set_step('flashrom', 'ok', detail)
        self._set_progress('', 0)
        self.tasks_done.append('flashrom')
    
    def step_ch341prog(self):
        """
        Copie ch341prog.exe + libusb-1.0.dll depuis resources/ embarques
        vers tools/ch341prog/.
        
        ch341prog est utilise pour lecture/ecriture car il offre une
        progression temps reel (fflush stdout), contrairement a flashrom
        qui bufferise sa sortie sous Windows.
        
        Le binaire est compile depuis le source dans le zip CH341A-Softwares
        (ch341prog-master 25xx), patche pour Windows (sigaction → 
        SetConsoleCtrlHandler + skip detach_kernel_driver), build via MinGW.
        """
        ch341_dir = TOOLS / 'ch341prog'
        ch341_exe = ch341_dir / 'ch341prog.exe'
        ch341_dll = ch341_dir / 'libusb-1.0.dll'
        
        # Sources embarques
        src_exe = RESOURCES / 'ch341prog' / 'ch341prog.exe'
        src_dll = RESOURCES / 'ch341prog' / 'libusb-1.0.dll'
        
        if not src_exe.exists() or not src_dll.exists():
            self._set_step('ch341prog', 'fail', L('detail.sources_missing'))
            msg = L('ch341prog.msg', exe=src_exe, dll=src_dll)
            messagebox.showwarning(L('ch341prog.title'), msg)
            raise Exception("ch341prog binaries missing in resources/")
        
        # Comparer les tailles : si identiques, on suppose meme version
        # Sinon (ou si fichier manquant), on copie depuis resources.
        # Ca permet de mettre a jour ch341prog automatiquement quand
        # une nouvelle version est livree dans le zip de l'app.
        needs_update = True
        if ch341_exe.exists() and ch341_dll.exists():
            try:
                same_exe = (ch341_exe.stat().st_size == src_exe.stat().st_size)
                same_dll = (ch341_dll.stat().st_size == src_dll.stat().st_size)
                if same_exe and same_dll:
                    needs_update = False
            except OSError:
                pass
        
        if not needs_update:
            self._set_step('ch341prog', 'ok', L('detail.up_to_date'))
            self.tasks_done.append('ch341prog')
            return
        
        self._set_step('ch341prog', 'doing', L('detail.copying'))
        
        try:
            ch341_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_exe, ch341_exe)
            shutil.copy2(src_dll, ch341_dll)
            
            self._set_step('ch341prog', 'ok',
                           f'{ch341_exe.stat().st_size // 1024} Ko')
            self.tasks_done.append('ch341prog')
        except Exception as e:
            self._set_step('ch341prog', 'fail', L('detail.copy_failed'))
            raise Exception(f"Impossible de copier ch341prog :\n{e}")
    
    def step_autopatcher(self):
        autopatch_dir = ROOT / 'lenovo_autopatcher'
        if (autopatch_dir / 'patch' / 'autopatch.py').exists():
            self._set_step('autopatcher', 'ok', L('detail.already_present'))
            self.tasks_done.append('autopatcher')
            return
        
        # Chercher le zip embarque
        embedded_zip = RESOURCES / 'lenovo_autopatcher_0.2.zip'
        
        if embedded_zip.exists():
            self._set_step('autopatcher', 'doing', L('detail.extracting'))
            try:
                with zipfile.ZipFile(embedded_zip, 'r') as zf:
                    zf.extractall(ROOT)
                self._set_step('autopatcher', 'ok', L('detail.extracted'))
                self.tasks_done.append('autopatcher')
                return
            except Exception as e:
                self._set_step('autopatcher', 'fail', L('detail.extract_failed'))
                raise
        
        # Sinon, demander a l'utilisateur de placer le zip
        self._set_step('autopatcher', 'fail', L('detail.zip_missing'))
        
        msg = L('autopatcher.msg', path=RESOURCES)
        messagebox.showwarning(L('autopatcher.title'), msg)
        raise Exception("Autopatcher missing — see message above.")
    
    def step_zadig(self):
        zadig = TOOLS / 'zadig.exe'
        if zadig.exists():
            self._set_step('zadig', 'ok', L('detail.already_present'))
            self.tasks_done.append('zadig')
            return
        
        self._set_step('zadig', 'doing', L('detail.downloading'))
        
        info = DOWNLOADS['zadig']
        
        def progress_cb(pct, downloaded, total):
            mb = downloaded / 1024 / 1024
            total_mb = total / 1024 / 1024
            self._set_progress(
                f"Zadig : {mb:.1f} / {total_mb:.1f} Mo", pct
            )
        
        try:
            download_file(info['url'], zadig, progress_cb)
        except Exception as e:
            self._set_step('zadig', 'fail', L('detail.dl_failed'))
            # Pas critique - on peut faire sans, on previendra plus tard
            self.tasks_failed.append('zadig')
            self._set_progress('', 0)
            return
        
        self._set_step('zadig', 'ok', f'{zadig.stat().st_size // 1024} KB')
        self._set_progress('', 0)
        self.tasks_done.append('zadig')
    
    def step_driver(self):
        self._set_step('driver', 'doing', L('detail.verifying'))
        
        driver_ok = check_libusb_driver()
        
        if driver_ok is True:
            self._set_step('driver', 'ok', L('detail.libusb_ok'))
            self.tasks_done.append('driver')
            return
        
        # Driver pas pret -> dialog Zadig
        self._set_step('driver', 'fail', L('detail.manual_setup'))
        self._show_zadig_wizard()
    
    def _show_zadig_wizard(self):
        """Wizard interactif pour installer le driver via Zadig."""
        wizard = Toplevel(self.root)
        wizard.title("Installation du driver CH341A")
        wizard.geometry("680x540")
        wizard.configure(bg=C['bg'])
        wizard.transient(self.root)
        wizard.grab_set()
        
        Label(wizard, text="🔌 Configuration du driver CH341A",
              font=('Segoe UI', 14, 'bold'),
              bg=C['bg'], fg=C['accent']
              ).pack(pady=(20, 5))
        
        Label(wizard, text="Une intervention manuelle est requise.",
              font=('Segoe UI', 10),
              bg=C['bg'], fg=C['fg_dim']
              ).pack(pady=(0, 15))
        
        instructions = (
            "Pour communiquer avec le CH341A, flashrom utilise libusb.\n"
            "Le driver natif Windows du CH341A n'est pas compatible.\n"
            "On va donc le remplacer via Zadig.\n\n"
            "ETAPES :\n\n"
            "1. Branche ton CH341A en USB sur ce PC\n\n"
            "2. Clique sur 'Lancer Zadig' ci-dessous\n"
            "   (Zadig va demander des droits admin — accepte)\n\n"
            "3. Dans Zadig :\n"
            "   a) Menu Options → coche 'List All Devices'\n"
            "   b) Dans la liste deroulante, selectionne :\n"
            "      → 'USB EEPROM Board' OU 'CH341A' OU 'WCH USB'\n"
            "   c) A droite, dans la cible du driver, choisis 'WinUSB'\n"
            "   d) Clique sur 'Replace Driver' (ou 'Install Driver')\n"
            "   e) Attends la confirmation, puis ferme Zadig\n\n"
            "4. Reviens ici et clique sur 'J'ai installe le driver'\n\n"
            "⚠️ ATTENTION : si tu utilises NeoProgrammer avec ce CH341A,\n"
            "il ne fonctionnera plus apres ce changement (driver different).\n"
            "Tu pourras toujours revenir au driver d'origine via Zadig."
        )
        
        text_frame = Frame(wizard, bg=C['bg_widget'])
        text_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        text_widget = tk.Text(text_frame, wrap='word',
                              bg=C['bg_widget'], fg=C['fg'],
                              font=('Segoe UI', 10),
                              relief='flat', padx=15, pady=10,
                              height=18)
        text_widget.pack(fill='both', expand=True)
        text_widget.insert('1.0', instructions)
        text_widget.config(state='disabled')
        
        # Buttons
        btn_frame = Frame(wizard, bg=C['bg'])
        btn_frame.pack(fill='x', padx=20, pady=15)
        
        def launch_zadig():
            zadig = TOOLS / 'zadig.exe'
            if not zadig.exists():
                messagebox.showerror("Zadig manquant",
                    "Zadig.exe n'a pas ete telecharge. Reessaie l'installation.")
                return
            try:
                # Lance Zadig en mode admin via PowerShell Start-Process -Verb RunAs
                subprocess.Popen([
                    'powershell', '-NoProfile', '-Command',
                    f"Start-Process -FilePath '{zadig}' -Verb RunAs"
                ])
            except Exception as e:
                messagebox.showerror("Lancement Zadig", str(e))
        
        def confirm_installed():
            wizard.destroy()
            # Re-verifier le driver
            self._set_step('driver', 'doing', L('detail.reverifying'))
            ok = check_libusb_driver()
            if ok is True:
                self._set_step('driver', 'ok', L('detail.configured'))
                self.tasks_done.append('driver')
            else:
                self._set_step('driver', 'fail', L('detail.verify_failed'))
                if messagebox.askyesno(
                    "Verification echouee",
                    "Le driver ne semble pas correctement installe.\n\n"
                    "Continuer quand meme ? (Tu pourras le reconfigurer plus tard)"
                ):
                    self.tasks_done.append('driver')
                else:
                    self.tasks_failed.append('driver')
        
        def skip_driver():
            if messagebox.askyesno(
                "Passer cette etape",
                "Tu pourras toujours configurer le driver plus tard via Zadig.\n\n"
                "Continuer ?"
            ):
                wizard.destroy()
                self._set_step('driver', 'fail', L('detail.manual_todo'))
                self.tasks_failed.append('driver')
        
        Button(btn_frame, text="🚀  Lancer Zadig",
               command=launch_zadig,
               font=('Segoe UI', 10, 'bold'),
               bg=C['accent'], fg=C['bg'],
               relief='flat', cursor='hand2', pady=8, borderwidth=0
              ).pack(side='left', fill='x', expand=True, padx=(0, 5))
        
        Button(btn_frame, text="✅  J'ai installe le driver",
               command=confirm_installed,
               font=('Segoe UI', 10, 'bold'),
               bg=C['success'], fg=C['bg'],
               relief='flat', cursor='hand2', pady=8, borderwidth=0
              ).pack(side='left', fill='x', expand=True, padx=5)
        
        Button(btn_frame, text="Passer",
               command=skip_driver,
               font=('Segoe UI', 10),
               bg=C['bg_widget'], fg=C['fg_dim'],
               relief='flat', cursor='hand2', pady=8, borderwidth=0
              ).pack(side='right', fill='x', expand=True, padx=(5, 0))
        
        wizard.wait_window()
    
    def finalize(self):
        # Sauvegarder config.json (preserve la langue existante si presente)
        existing_lang = _LANG
        try:
            if CONFIG_FILE.exists():
                old = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
                existing_lang = old.get('language', _LANG)
        except Exception:
            pass
        
        config = {
            'flashrom_path': str(TOOLS / 'flashrom.exe'),
            'ch341prog_path': str(TOOLS / 'ch341prog' / 'ch341prog.exe'),
            'autopatcher_dir': str(ROOT / 'lenovo_autopatcher'),
            'dumps_dir': str(DUMPS),
            'reports_dir': str(REPORTS),
            'logs_dir': str(LOGS),
            'chip_name': '',
            'language': existing_lang,
        }
        CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding='utf-8')
        
        critical_failed = [t for t in ['flashrom', 'autopatcher'] if t in self.tasks_failed]
        
        if critical_failed:
            self.action_btn.config(state='normal',
                                    text=L('finalize.btn_failed',
                                           failed=", ".join(critical_failed)),
                                    bg=C['error'])
            messagebox.showerror(
                L('finalize.incomplete_title'),
                L('finalize.incomplete_msg', failed=', '.join(critical_failed))
            )
            sys.exit(1)
        
        if 'driver' in self.tasks_failed:
            self.action_btn.config(state='normal',
                                    text=L('finalize.btn_warn'),
                                    bg=C['warning'],
                                    command=self.exit_ok)
        else:
            self.action_btn.config(state='normal',
                                    text=L('finalize.btn_ok'),
                                    bg=C['success'],
                                    command=self.exit_ok)
    
    def exit_ok(self):
        self.root.destroy()
        sys.exit(0)


# ════ MAIN ══════════════════════════════════════════════════════
def main():
    # Cas trivial : si tout est deja installe, on sort tout de suite
    flashrom_ok = (TOOLS / 'flashrom.exe').exists()
    autopatcher_ok = (ROOT / 'lenovo_autopatcher' / 'patch' / 'autopatch.py').exists()
    config_ok = CONFIG_FILE.exists()
    
    if flashrom_ok and autopatcher_ok and config_ok:
        # Tout pret, on cree juste les dossiers de travail si besoin
        for d in (DUMPS, REPORTS, LOGS):
            d.mkdir(parents=True, exist_ok=True)
        print("Installation deja complete.")
        sys.exit(0)
    
    # Sinon on lance l'UI
    root = Tk()
    InstallerUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
