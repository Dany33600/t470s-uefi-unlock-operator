"""
T470s UEFI Unlock Operator — GUI principale.
"""
import json
import threading
from datetime import datetime
from pathlib import Path
from tkinter import Tk, Frame, Label, Button, Text, Scrollbar, Toplevel, Entry, StringVar
from tkinter import messagebox, ttk
import tkinter as tk

from flashrom_wrapper import (
    FlashromWrapper, ChipNotDetectedError, FlashromError, 
    WriteVerifyError, DriverNotInstalledError
)
from ch341prog_wrapper import (
    Ch341progWrapper, Ch341progError, Ch341progNotFoundError, Ch341progDriverError
)
from autopatch_wrapper import patch_rom, AutopatchError
from sn_extractor import extract_sn, md5_of_file
from session_logger import SessionLogger, make_session_csv_path
from zadig_wizard import ZadigWizard
from i18n import (
    t, set_language, get_language,
    detect_language_from_args, load_language_from_config, save_language_to_config,
)


# Chemins (relatifs au root du projet)
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
CONFIG_FILE = ROOT / 'config.json'


# ═══════════════════════════════════════════════════════════════
# THEME
# ═══════════════════════════════════════════════════════════════
C = {
    'bg':         '#1a1b26',
    'bg_alt':     '#24283b',
    'bg_widget':  '#2f334d',
    'fg':         '#c0caf5',
    'fg_dim':     '#a9b1d6',
    'accent':     '#7aa2f7',
    'success':    '#9ece6a',
    'warning':    '#e0af68',
    'error':      '#f7768e',
    'border':     '#414868',
}

FONT_MAIN = ('Segoe UI', 10)
FONT_TITLE = ('Segoe UI', 14, 'bold')
FONT_STEP = ('Segoe UI', 11, 'bold')
FONT_MONO = ('Consolas', 9)


DEFAULT_CONFIG = {
    'flashrom_path': str(ROOT / 'tools' / 'flashrom.exe'),
    'ch341prog_path': str(ROOT / 'tools' / 'ch341prog' / 'ch341prog.exe'),
    'autopatcher_dir': str(ROOT / 'lenovo_autopatcher'),
    'dumps_dir': str(ROOT / 'dumps'),
    'reports_dir': str(ROOT / 'reports'),
    'logs_dir': str(ROOT / 'logs'),
    'chip_name': '',
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        return {**DEFAULT_CONFIG, **cfg}
    CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding='utf-8')
    return DEFAULT_CONFIG.copy()


# ═══════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════
class OperatorApp:
    def __init__(self, root: Tk):
        self.root = root
        self.config = load_config()
        self.flashrom = FlashromWrapper(
            flashrom_path=self.config['flashrom_path'],
            chip_name=self.config['chip_name'] or None,
        )
        # ch341prog est utilise en priorite pour les operations de
        # lecture/ecriture car il offre une progression temps reel
        # (fflush apres chaque update), contrairement a flashrom 1.4
        # qui bufferise sa sortie.
        self.ch341prog = Ch341progWrapper(
            ch341prog_path=self.config['ch341prog_path'],
        )
        self.csv_path = make_session_csv_path(self.config['reports_dir'])
        self.logger = SessionLogger(self.csv_path)
        
        # Fichier de log texte (tout ce qui est ecrit dans la console UI
        # y est aussi ecrit en direct, pour debug et traçabilite)
        logs_dir = Path(self.config['logs_dir'])
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_filename = f"session_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log"
        self.log_file_path = str(logs_dir / log_filename)
        try:
            # Buffer ligne par ligne pour flush immediat
            self._log_fh = open(self.log_file_path, 'w', encoding='utf-8', buffering=1)
            self._log_fh.write(
                f"# T470s UEFI Unlock Operator — log de session\n"
                f"# Demarre : {datetime.now().isoformat()}\n"
                f"# CSV     : {self.csv_path}\n"
                f"# ----------------------------------------\n"
            )
            self._log_fh.flush()
        except Exception:
            self._log_fh = None  # log fichier optionnel, ne doit pas planter l'app
        
        self.current_step = 0
        self.machine_data = {}
        
        self._build_ui()
        self._log("✨ Session démarrée. CSV : " + self.csv_path)
        if self._log_fh:
            self._log(f"📝 Log fichier : {self.log_file_path}")
        self._reset_machine()
    
    def _build_ui(self):
        self.root.title(t('app.title'))
        self.root.geometry("1100x720")
        self.root.configure(bg=C['bg'])
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Dark.Horizontal.TProgressbar',
                        background=C['accent'],
                        troughcolor=C['bg_widget'],
                        bordercolor=C['border'],
                        lightcolor=C['accent'],
                        darkcolor=C['accent'])
        
        # Header
        header = Frame(self.root, bg=C['bg_alt'], height=70)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        Label(header, text=f"🔓 {t('app.title')}",
              font=FONT_TITLE, bg=C['bg_alt'], fg=C['accent']
              ).pack(side='left', padx=20, pady=15)
        
        self.session_info = Label(
            header,
            text=f"{t('ui.machines_count', n=0)} ✅  /  {t('ui.session_file', file=Path(self.csv_path).name)}",
            font=FONT_MAIN, bg=C['bg_alt'], fg=C['fg_dim']
        )
        self.session_info.pack(side='right', padx=20)
        
        main = Frame(self.root, bg=C['bg'])
        main.pack(fill='both', expand=True, padx=15, pady=10)
        
        # Left
        left = Frame(main, bg=C['bg_alt'], width=520)
        left.pack(side='left', fill='both', expand=True, padx=(0, 8))
        
        Label(left, text=f"📋 {t('ui.workflow')}", font=FONT_TITLE,
              bg=C['bg_alt'], fg=C['fg']
              ).pack(anchor='w', padx=15, pady=(15, 5))
        
        self.step_label = Label(
            left, text=t('workflow.ready_title'),
            font=FONT_STEP, bg=C['bg_alt'], fg=C['accent']
        )
        self.step_label.pack(anchor='w', padx=15)
        
        self.progress = ttk.Progressbar(
            left, mode='determinate', style='Dark.Horizontal.TProgressbar', maximum=7
        )
        self.progress.pack(fill='x', padx=15, pady=(5, 8))
        
        # ─── Zone de progression "opération en cours" ───────────
        # Affichee uniquement pendant les operations longues
        # (read / write / patch).
        self.op_frame = Frame(left, bg=C['bg_widget'],
                               highlightbackground=C['border'],
                               highlightthickness=1)
        # On ne la pack pas tout de suite : on l'affichera dynamiquement
        
        op_header = Frame(self.op_frame, bg=C['bg_widget'])
        op_header.pack(fill='x', padx=10, pady=(8, 2))
        
        self.op_label = Label(
            op_header, text="",
            font=FONT_STEP, bg=C['bg_widget'], fg=C['accent']
        )
        self.op_label.pack(side='left')
        
        self.op_percent = Label(
            op_header, text="",
            font=('Segoe UI', 11, 'bold'),
            bg=C['bg_widget'], fg=C['fg']
        )
        self.op_percent.pack(side='right')
        
        self.op_progress = ttk.Progressbar(
            self.op_frame, mode='determinate',
            style='Dark.Horizontal.TProgressbar', maximum=100
        )
        self.op_progress.pack(fill='x', padx=10, pady=(0, 4))
        
        self.op_status = Label(
            self.op_frame, text="",
            font=('Segoe UI', 9), bg=C['bg_widget'], fg=C['fg_dim']
        )
        self.op_status.pack(anchor='w', padx=10, pady=(0, 8))
        
        # State pour suivre la progression
        self._op_start_time = None
        self._op_visible = False
        
        # Instructions
        instr_frame = Frame(left, bg=C['bg_widget'],
                            highlightbackground=C['border'], highlightthickness=1)
        instr_frame.pack(fill='both', expand=True, padx=15, pady=(0, 15))
        
        Label(instr_frame, text=t('ui.instructions'),
              font=FONT_STEP, bg=C['bg_widget'], fg=C['warning']
              ).pack(anchor='w', padx=10, pady=(8, 4))
        
        self.instructions = Text(
            instr_frame, height=8, wrap='word',
            bg=C['bg_widget'], fg=C['fg'],
            font=FONT_MAIN, relief='flat',
            insertbackground=C['fg'],
        )
        self.instructions.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        self.instructions.config(state='disabled')
        
        # Machine info
        info_frame = Frame(left, bg=C['bg_widget'],
                           highlightbackground=C['border'], highlightthickness=1)
        info_frame.pack(fill='x', padx=15, pady=(0, 15))
        
        Label(info_frame, text=t('ui.machine_current'),
              font=FONT_STEP, bg=C['bg_widget'], fg=C['success']
              ).pack(anchor='w', padx=10, pady=(8, 4))
        
        self.machine_info = Label(
            info_frame, text=t('ui.machine_none'),
            font=FONT_MONO, bg=C['bg_widget'], fg=C['fg_dim'],
            justify='left', anchor='w'
        )
        self.machine_info.pack(fill='x', padx=10, pady=(0, 10))
        
        # Buttons
        btn_frame = Frame(left, bg=C['bg_alt'])
        btn_frame.pack(fill='x', padx=15, pady=(0, 15))
        
        self.action_btn = self._make_btn(btn_frame, t('workflow.start_machine'),
                                          self.action_main, C['accent'])
        self.action_btn.pack(fill='x', pady=2)
        
        btn_row = Frame(btn_frame, bg=C['bg_alt'])
        btn_row.pack(fill='x', pady=2)
        
        self.skip_btn = self._make_btn(btn_row, t('btn.skip_machine'),
                                        self.skip_machine, C['warning'])
        self.skip_btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
        
        self.finish_btn = self._make_btn(btn_row, t('btn.end_session'),
                                          self.finish_session, C['error'])
        self.finish_btn.pack(side='right', fill='x', expand=True, padx=(4, 0))
        
        # Right (console)
        right = Frame(main, bg=C['bg_alt'])
        right.pack(side='right', fill='both', expand=True, padx=(8, 0))
        
        Label(right, text=f"📜 {t('ui.console')}", font=FONT_TITLE,
              bg=C['bg_alt'], fg=C['fg']
              ).pack(anchor='w', padx=15, pady=(15, 5))
        
        log_frame = Frame(right, bg=C['bg_widget'])
        log_frame.pack(fill='both', expand=True, padx=15, pady=(0, 15))
        
        scrollbar = Scrollbar(log_frame, bg=C['bg_widget'])
        scrollbar.pack(side='right', fill='y')
        
        self.log_text = Text(
            log_frame, wrap='word',
            bg='#16161e', fg=C['fg'],
            font=FONT_MONO, relief='flat',
            yscrollcommand=scrollbar.set,
            insertbackground=C['fg'],
        )
        self.log_text.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        self.log_text.tag_configure('success', foreground=C['success'])
        self.log_text.tag_configure('warning', foreground=C['warning'])
        self.log_text.tag_configure('error', foreground=C['error'])
        self.log_text.tag_configure('info', foreground=C['accent'])
        self.log_text.tag_configure('dim', foreground=C['fg_dim'])
        self.log_text.config(state='disabled')
    
    def _make_btn(self, parent, text, command, color):
        return Button(parent, text=text, command=command,
                       font=FONT_MAIN, bg=color, fg=C['bg'],
                       activebackground=C['border'],
                       activeforeground=C['fg'],
                       relief='flat', cursor='hand2', pady=8,
                       borderwidth=0)
    
    def _log(self, msg: str, tag: str = ''):
        timestamp = datetime.now().strftime('%H:%M:%S')
        # UI
        self.log_text.config(state='normal')
        self.log_text.insert('end', f'[{timestamp}] ', 'dim')
        self.log_text.insert('end', msg + '\n', tag)
        self.log_text.see('end')
        self.log_text.config(state='disabled')
        self.root.update_idletasks()
        # Fichier (en direct, ligne par ligne)
        if self._log_fh:
            try:
                # Tag entre crochets pour indiquer le niveau (info/success/error/...)
                tag_part = f" [{tag}]" if tag else ""
                self._log_fh.write(f"[{timestamp}]{tag_part} {msg}\n")
                self._log_fh.flush()
            except Exception:
                pass
    
    def _set_instructions(self, text: str):
        self.instructions.config(state='normal')
        self.instructions.delete('1.0', 'end')
        self.instructions.insert('1.0', text)
        self.instructions.config(state='disabled')
    
    def _set_step(self, step: int, title: str):
        self.current_step = step
        self.step_label.config(text=t('ui.step_n_of_total', n=step, title=title))
        self.progress['value'] = step
    
    def _set_action_btn(self, text: str, command, color=None):
        self.action_btn.config(text=text, command=command,
                                bg=color or C['accent'], state='normal')
    
    # ─── Gestion de la barre de progression d'operation ───────
    def _show_operation(self, label: str):
        """Affiche la zone de progression operation et la reset."""
        if not self._op_visible:
            self.op_frame.pack(fill='x', padx=15, pady=(0, 8),
                                before=self.action_btn.master)
            self._op_visible = True
        self.op_label.config(text=label)
        self.op_percent.config(text="0%")
        self.op_progress['value'] = 0
        self.op_status.config(text=t('op.initializing'))
        self._op_start_time = datetime.now()
        self.root.update_idletasks()
    
    def _update_operation(self, percent: int, status: str = None):
        """Met a jour la progression (0-100) et le status optionnel."""
        if not self._op_visible:
            return
        percent = max(0, min(100, percent))
        self.op_progress['value'] = percent
        self.op_percent.config(text=f"{percent}%")
        
        if self._op_start_time:
            elapsed = (datetime.now() - self._op_start_time).total_seconds()
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            elapsed_str = f"{mins:02d}:{secs:02d}"
            
            # Estimer le temps restant
            if percent > 5:
                total_estimated = elapsed * 100 / percent
                remaining = total_estimated - elapsed
                rmins = int(remaining // 60)
                rsecs = int(remaining % 60)
                eta_str = t('op.eta_label', mins=rmins, secs=rsecs)
            else:
                eta_str = t('op.calculating')
            
            if status:
                self.op_status.config(text=t(
                    'op.elapsed_eta', status=status,
                    elapsed=elapsed_str, eta=eta_str
                ))
            else:
                self.op_status.config(text=t(
                    'op.elapsed', elapsed=elapsed_str, eta=eta_str
                ))
        elif status:
            self.op_status.config(text=status)
        
        self.root.update_idletasks()
    
    def _hide_operation(self):
        """Cache la zone de progression operation."""
        if self._op_visible:
            self.op_frame.pack_forget()
            self._op_visible = False
        self._op_start_time = None
    
    def _parse_flashrom_progress(self, line: str) -> tuple:
        """
        Parse une ligne de sortie flashrom pour extraire le pourcentage
        et un status. Retourne (percent, status) ou (None, None) si
        la ligne ne contient pas d'info de progression.
        
        flashrom 1.4 avec --progress affiche plusieurs formats :
        - "Reading flash... " puis "Reading: XX%"
        - "Erasing and writing flash chip... XX%"
        - "Verifying flash... XX%"
        - Lignes "[████████████████      ] 67% Reading"
        """
        import re
        
        # Pattern 1 : "XX%" dans la ligne (le plus generique)
        m = re.search(r'(\d{1,3})\s*%', line)
        if m:
            percent = int(m.group(1))
            # Detecter la phase courante
            line_lower = line.lower()
            if 'read' in line_lower:
                status = "Lecture en cours"
            elif 'eras' in line_lower:
                status = "Effacement en cours"
            elif 'writ' in line_lower:
                status = "Ecriture en cours"
            elif 'verif' in line_lower:
                status = "Verification en cours"
            else:
                status = None
            return percent, status
        
        # Pattern 2 : mots-cles sans pourcentage (changement de phase)
        line_lower = line.lower()
        if 'reading old flash chip contents' in line_lower:
            return 0, "Lecture initiale"
        if 'erasing and writing flash chip' in line_lower:
            return 33, "Effacement + ecriture"
        if 'verifying flash' in line_lower:
            return 90, "Verification"
        if 'verified' in line_lower:
            return 100, "Termine"
        
        return None, None
    
    def _flashrom_progress_callback(self, line: str):
        """Callback pour les operations flashrom. Loggue + met a jour
        la barre de progression operation."""
        self._log(f"  {line}", 'dim')
        percent, status = self._parse_flashrom_progress(line)
        if percent is not None:
            self._update_operation(percent, status)
    
    # ─── Dialog de confirmation du SN detecte ──────────────────
    def _ask_sn_confirmation(self, detected_sn, mtm, bios_version, confidence):
        """
        Affiche un dialog modal pour confirmer/corriger le SN detecte.
        S'execute dans le thread principal Tk (appele depuis un worker
        thread via root.after, mais le dialog doit etre sync).
        
        Retourne le SN confirme (str) ou None si annulation.
        """
        # On a besoin de bloquer le worker thread jusqu'a la decision
        # de l'utilisateur. On utilise un threading.Event.
        import threading
        result = {'sn': None, 'cancelled': False}
        done_event = threading.Event()
        
        def show_dialog():
            dialog = Toplevel(self.root)
            dialog.title(t('dialog.sn_title'))
            dialog.geometry("560x420")
            dialog.configure(bg=C['bg'])
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Centrer
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() - 560) // 2
            y = (dialog.winfo_screenheight() - 420) // 2
            dialog.geometry(f"+{x}+{y}")
            
            # Header
            Label(dialog, text=t('dialog.sn_header'),
                  font=('Segoe UI', 14, 'bold'),
                  bg=C['bg'], fg=C['accent']
                  ).pack(pady=(20, 5))
            
            # Niveau de confiance
            confidence_colors = {
                'high': (C['success'], t('dialog.sn_confidence_high')),
                'medium': (C['warning'], t('dialog.sn_confidence_medium')),
                'low': (C['warning'], t('dialog.sn_confidence_low')),
                'none': (C['error'], t('dialog.sn_confidence_none')),
            }
            conf_color, conf_text = confidence_colors.get(
                confidence, (C['fg_dim'], confidence)
            )
            Label(dialog, text=conf_text,
                  font=('Segoe UI', 10, 'bold'),
                  bg=C['bg'], fg=conf_color
                  ).pack(pady=(0, 15))
            
            # Infos detectees
            info_frame = Frame(dialog, bg=C['bg_widget'])
            info_frame.pack(fill='x', padx=30, pady=(0, 15))
            
            unknown = t('dialog.sn_unknown')
            for label_text, value in [
                (t('dialog.sn_mtm_label'), mtm or unknown),
                (t('dialog.sn_bios_label'), bios_version or unknown),
            ]:
                row = Frame(info_frame, bg=C['bg_widget'])
                row.pack(fill='x', padx=15, pady=4)
                Label(row, text=label_text, width=18, anchor='w',
                      font=('Segoe UI', 10),
                      bg=C['bg_widget'], fg=C['fg_dim']
                      ).pack(side='left')
                Label(row, text=value, anchor='w',
                      font=('Consolas', 10, 'bold'),
                      bg=C['bg_widget'], fg=C['fg']
                      ).pack(side='left')
            
            # Champ SN editable
            Label(dialog, 
                  text=t('dialog.sn_prompt'),
                  font=('Segoe UI', 10),
                  bg=C['bg'], fg=C['fg'], justify='center'
                  ).pack(pady=(5, 8))
            
            sn_var = StringVar(value=detected_sn or '')
            sn_entry = Entry(
                dialog, textvariable=sn_var,
                font=('Consolas', 14, 'bold'),
                bg=C['bg_widget'], fg=C['accent'],
                insertbackground=C['fg'],
                relief='flat', justify='center', width=15,
            )
            sn_entry.pack(pady=(0, 5))
            sn_entry.focus_set()
            sn_entry.select_range(0, 'end')
            
            # Hint
            Label(dialog, 
                  text=t('dialog.sn_hint'),
                  font=('Segoe UI', 8),
                  bg=C['bg'], fg=C['fg_dim']
                  ).pack(pady=(0, 15))
            
            # Boutons
            btn_frame = Frame(dialog, bg=C['bg'])
            btn_frame.pack(side='bottom', fill='x', padx=30, pady=15)
            
            def on_confirm():
                sn = sn_var.get().strip().upper()
                if not sn:
                    messagebox.showwarning(
                        t('dialog.sn_empty_warn_title'),
                        t('dialog.sn_empty_warn'),
                        parent=dialog)
                    return
                if not all(c.isalnum() for c in sn):
                    messagebox.showwarning(
                        t('dialog.sn_invalid_warn_title'),
                        t('dialog.sn_invalid_warn'),
                        parent=dialog)
                    return
                result['sn'] = sn
                done_event.set()
                dialog.destroy()
            
            def on_cancel():
                result['cancelled'] = True
                done_event.set()
                dialog.destroy()
            
            Button(btn_frame, text=t('dialog.sn_confirm_btn'),
                   command=on_confirm,
                   font=('Segoe UI', 10, 'bold'),
                   bg=C['success'], fg=C['bg'],
                   relief='flat', cursor='hand2', pady=8, borderwidth=0,
                  ).pack(side='left', fill='x', expand=True, padx=(0, 5))
            
            Button(btn_frame, text=t('btn.cancel'),
                   command=on_cancel,
                   font=('Segoe UI', 10),
                   bg=C['bg_widget'], fg=C['fg_dim'],
                   relief='flat', cursor='hand2', pady=8, borderwidth=0,
                  ).pack(side='right', fill='x', expand=True, padx=(5, 0))
            
            # Bind Enter pour confirmer
            dialog.bind('<Return>', lambda e: on_confirm())
            dialog.bind('<Escape>', lambda e: on_cancel())
            dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        
        # Lancer le dialog dans le thread Tk principal
        self.root.after(0, show_dialog)
        
        # Bloquer le worker thread jusqu'a la decision
        done_event.wait()
        
        if result['cancelled']:
            return None
        return result['sn']
    
    def _update_machine_info(self):
        m = self.machine_data
        if not m or not m.get('start_time'):
            self.machine_info.config(text=t('ui.machine_none'))
            return
        lines = []
        if m.get('sn'):
            lines.append(f"{t('machine.sn'):<10}: {m['sn']}")
        if m.get('mtm'):
            lines.append(f"{t('machine.mtm'):<10}: {m['mtm']}")
        if m.get('bios_version'):
            lines.append(f"{t('machine.bios'):<10}: {m['bios_version']}")
        if m.get('chip'):
            lines.append(
                f"{t('machine.chip'):<10}: {m['chip']['vendor']} "
                f"{m['chip']['name']} ({m['chip']['size_kb']} kB)"
            )
        if m.get('stock_md5'):
            lines.append(f"{t('machine.md5_stock'):<10}: {m['stock_md5'][:16]}...")
        self.machine_info.config(text='\n'.join(lines) if lines else '(...)')
    
    def _update_session_info(self):
        summary = self.logger.session_summary()
        self.session_info.config(
            text=f"{t('ui.machines_count', n=summary['success'])} ✅ / "
                 f"{summary['failed']} ❌  •  "
                 f"{t('ui.session_file', file=Path(self.csv_path).name)}"
        )
    
    def _reset_machine(self):
        self.machine_data = {
            'start_time': None, 'sn': None, 'mtm': None, 'bios_version': None,
            'chip': None, 'stock_path': None, 'patched_path': None,
            'stock_md5': None, 'patched_md5': None,
            'verify_patched': '', 'verify_restore': '', 'notes': [],
        }
        self._update_machine_info()
        self._set_step(0, t('workflow.ready_title').split('— ')[-1])
        self._set_instructions(t('workflow.ready_instructions'))
        self._set_action_btn(t('workflow.start_machine'), self.action_main)
    
    def action_main(self):
        actions = {
            0: self.step1_detect_chip,
            1: self.step2_dump_stock,
            2: self.step3_patch,
            3: self.step4_write_patched,
            4: self.step5_wait_bios_sequence,
            5: self.step6_write_restore,
            6: self.step7_finalize,
        }
        action = actions.get(self.current_step)
        if action:
            self.action_btn.config(state='disabled')
            threading.Thread(target=action, daemon=True).start()
    
    # ════ STEP 1 ════════════════════════════════════════════════
    def step1_detect_chip(self):
        self._set_step(1, t('step.detect'))
        self._log(t('workflow.detecting'), 'info')
        self._set_instructions(t('workflow.detecting_instructions'))
        
        try:
            chip = self.flashrom.detect_chip(on_progress=lambda l: self._log(f"  {l}", 'dim'))
            self.machine_data['chip'] = chip
            self.machine_data['start_time'] = datetime.now()
            
            # IMPORTANT : memoriser le nom de la puce pour les commandes
            # suivantes (cf. commentaires precedents)
            self.flashrom.chip_name = chip['name']
            
            self._log(t('workflow.chip_detected',
                        vendor=chip['vendor'], name=chip['name'],
                        size=chip['size_kb']), 'success')
            self._update_machine_info()
            
            self.root.after(0, lambda: self._set_instructions(
                t('workflow.chip_detected_instructions',
                  vendor=chip['vendor'], name=chip['name'])
            ))
            self.root.after(0, lambda: self._set_action_btn(
                t('workflow.read_chip_btn'), self.action_main))
            self.current_step = 1
        except DriverNotInstalledError as e:
            self._log(t('err.driver_not_installed_warn'), 'warning')
            self.root.after(0, self._show_zadig_wizard_inline)
        except ChipNotDetectedError as e:
            self._log(f"❌ {e}", 'error')
            self.root.after(0, lambda: messagebox.showerror(
                t('err.detect_failed_title'), str(e)))
            self.root.after(0, lambda: self.action_btn.config(state='normal'))
    
    def _show_zadig_wizard_inline(self):
        """Ouvre le wizard Zadig depuis l'app principale (pas l'installeur).
        Une fois ferme avec succes, relance automatiquement la detection."""
        self._set_instructions(
            "Configuration du driver requise.\n\n"
            "Une fenetre va s'ouvrir pour t'aider a configurer le driver "
            "libusb via Zadig. Cette manipulation n'est a faire qu'UNE FOIS."
        )
        
        def retest_callback():
            """Callback appele quand l'utilisateur clique 'Re-tester' dans le wizard."""
            try:
                chip = self.flashrom.detect_chip()
                return True
            except Exception:
                return False
        
        wizard = ZadigWizard(
            parent=self.root,
            on_retest_callback=retest_callback,
            first_install=False,
        )
        
        # Bloque jusqu'a la fermeture du wizard
        success = wizard.wait()
        
        if success:
            self._log("✅ Driver libusb configuré avec succès", 'success')
            self._set_instructions(
                "Driver configuré. La détection va reprendre automatiquement."
            )
            # On relance la step 1 (qui va maintenant fonctionner)
            self.current_step = 0
            self.root.after(500, self.action_main)
        else:
            self._log("⚠️ Configuration du driver annulée ou échouée", 'warning')
            self._set_instructions(
                "Driver pas encore configuré.\n\n"
                "Tu peux retenter en cliquant à nouveau sur 'Démarrer cette machine'.\n"
                "Ou lance manuellement tools/zadig.exe en admin."
            )
            self.action_btn.config(state='normal')
    
    # ════ STEP 2 ════════════════════════════════════════════════
    def step2_dump_stock(self):
        self._set_step(2, t('step.read'))
        self._log(t('workflow.reading'), 'info')
        self._set_instructions(t('workflow.reading_instructions'))
        self.root.after(0, lambda: self._show_operation(t('workflow.read_op_title')))
        
        dumps_dir = Path(self.config['dumps_dir'])
        dumps_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = dumps_dir / f"_tmp_{datetime.now().strftime('%H%M%S')}.rom"
        
        try:
            def on_progress_cb(percent, status):
                self.root.after(0, lambda p=percent, s=status: self._update_operation(p, s))
            
            self.ch341prog.read(
                str(tmp_path),
                on_log=lambda l: self._log(f"  {l}", 'dim'),
                on_progress=on_progress_cb,
            )
            self._log(t('workflow.read_done'), 'success')
            self.root.after(0, lambda: self._update_operation(100, t('op.finished')))
            
            self._log(t('workflow.analyzing'), 'info')
            info = extract_sn(str(tmp_path))
            
            detected_sn = info['sn']
            confidence = info['confidence']
            
            self._log(t('workflow.sn_detected',
                        sn=detected_sn, conf=confidence),
                      'success' if confidence == 'high' else 'warning')
            self._log(t('workflow.mtm_detected', mtm=info['mtm']), 'dim')
            self._log(t('workflow.bios_detected', bios=info['bios_version']), 'dim')
            
            # Demande confirmation a l'utilisateur sur le SN
            self.root.after(0, self._hide_operation)
            
            confirmed_sn = self._ask_sn_confirmation(
                detected_sn, info['mtm'], info['bios_version'], confidence
            )
            
            if confirmed_sn is None:
                self._log(t('err.aborted_by_user'), 'warning')
                if tmp_path.exists():
                    tmp_path.unlink()
                self.root.after(0, lambda: self.action_btn.config(state='normal'))
                return
            
            sn = confirmed_sn
            if sn != detected_sn:
                self._log("  " + t('dialog.sn_corrected_note', sn=sn), 'info')
                self.machine_data['notes'].append(
                    f"SN corrected: detected={detected_sn}, used={sn}")
            
            self.machine_data.update({
                'sn': sn,
                'mtm': info['mtm'] or 'unknown',
                'bios_version': info['bios_version'] or 'unknown',
            })
            
            machine_dir = dumps_dir / sn
            machine_dir.mkdir(exist_ok=True)
            final_stock_path = machine_dir / f"stock_{sn}.rom"
            
            if final_stock_path.exists():
                i = 2
                while (machine_dir / f"stock_{sn}_v{i}.rom").exists():
                    i += 1
                final_stock_path = machine_dir / f"stock_{sn}_v{i}.rom"
                self.machine_data['notes'].append(f"redump v{i}")
            
            tmp_path.rename(final_stock_path)
            self.machine_data['stock_path'] = str(final_stock_path)
            self.machine_data['stock_md5'] = md5_of_file(str(final_stock_path))
            
            self._log(t('workflow.md5_stock', md5=self.machine_data['stock_md5']), 'dim')
            self._log(t('workflow.saved_at', path=final_stock_path), 'dim')
            
            self.root.after(0, self._update_machine_info)
            self.root.after(0, lambda: self._set_instructions(
                t('workflow.dump_saved_instructions', sn=sn)
            ))
            self.root.after(0, lambda: self._set_action_btn(
                t('workflow.patch_btn'), self.action_main))
            self.current_step = 2
        except (FlashromError, Ch341progError) as e:
            self._log(t('err.read_failed', err=e), 'error')
            if tmp_path.exists():
                tmp_path.unlink()
            self.root.after(0, self._hide_operation)
            self.root.after(0, lambda: messagebox.showerror(
                t('err.read_failed_title'), str(e)))
            self.root.after(0, lambda: self.action_btn.config(state='normal'))
        except Exception as e:
            self._log(f"❌ {e}", 'error')
            self.root.after(0, self._hide_operation)
            self.root.after(0, lambda: self.action_btn.config(state='normal'))
    
    # ════ STEP 3 ════════════════════════════════════════════════
    def step3_patch(self):
        self._set_step(3, t('step.patch'))
        self._log(t('workflow.patching'), 'info')
        self._set_instructions(t('workflow.patching_instructions'))
        self.root.after(0, lambda: self._show_operation(t('workflow.patch_op_title')))
        
        # Progression "factice" pour le patch (rapide, ~10s)
        # On simule une progression par etape du patch
        patch_progress = {'value': 0}
        
        def on_patch_line(line):
            self._log(f"  {line}", 'dim')
            line_lower = line.lower()
            # Detecter les phases du patch
            if 'using uefireplace' in line_lower:
                patch_progress['value'] = 20
            elif 'looking for volumes' in line_lower:
                patch_progress['value'] = 60
            elif 'replacing volume' in line_lower:
                patch_progress['value'] = 80
            elif 'done.' in line_lower or 'patch file' in line_lower:
                patch_progress['value'] = 100
            elif '[' in line and '/' in line:
                import re
                m = re.search(r'\[(\d+)/(\d+)\]', line)
                if m:
                    cur, total = int(m.group(1)), int(m.group(2))
                    patch_progress['value'] = 20 + int(60 * cur / total)
            
            self.root.after(0, lambda v=patch_progress['value']:
                            self._update_operation(v, t('workflow.patch_status')))
        
        try:
            patched_path = patch_rom(
                self.config['autopatcher_dir'],
                self.machine_data['stock_path'],
                on_progress=on_patch_line
            )
            self.machine_data['patched_path'] = patched_path
            self.machine_data['patched_md5'] = md5_of_file(patched_path)
            self._log(t('workflow.patch_done', file=Path(patched_path).name), 'success')
            self._log(t('workflow.md5_patched', md5=self.machine_data['patched_md5']), 'dim')
            self.root.after(0, lambda: self._update_operation(100, t('op.finished')))
            self.root.after(800, self._hide_operation)
            
            self.root.after(0, lambda: self._set_instructions(
                t('workflow.patched_ready_instructions')
            ))
            self.root.after(0, lambda: self._set_action_btn(
                t('workflow.write_patched_btn'), self.action_main, C['warning']))
            self.current_step = 3
        except AutopatchError as e:
            self._log(t('err.patch_failed', err=e), 'error')
            self.root.after(0, self._hide_operation)
            self.root.after(0, lambda: messagebox.showerror(
                t('err.patch_failed_title'), str(e)))
            self.root.after(0, lambda: self.action_btn.config(state='normal'))
    
    # ════ STEP 4 ════════════════════════════════════════════════
    def step4_write_patched(self):
        self._set_step(4, t('step.write_patched'))
        self._log(t('workflow.writing_patched'), 'info')
        self._set_instructions(t('workflow.writing_instructions'))
        self.root.after(0, lambda: self._show_operation(t('workflow.write_op_title')))
        
        try:
            def on_progress_cb(percent, status):
                self.root.after(0, lambda p=percent, s=status: self._update_operation(p, s))
            
            self.ch341prog.write(
                self.machine_data['patched_path'],
                on_log=lambda l: self._log(f"  {l}", 'dim'),
                on_progress=on_progress_cb,
            )
            self._log(t('workflow.write_done_verifying'), 'dim')
            
            # VERIFY : on relit la puce et on compare au fichier source
            self.root.after(0, lambda: self._update_operation(0, t('op.verification')))
            
            def on_verify_progress_cb(percent, status):
                # On reformate le status pour dire "Verif" au lieu de "Lecture"
                vstatus = status.replace("Lecture :", "Verif :").replace("Read:", "Verify:")
                self.root.after(0, lambda p=percent, s=vstatus: self._update_operation(p, s))
            
            verify_ok = self.ch341prog.verify(
                self.machine_data['patched_path'],
                on_log=lambda l: self._log(f"  {l}", 'dim'),
                on_progress=on_verify_progress_cb,
            )
            
            if not verify_ok:
                raise Ch341progError(t('err.verify_failed_patched'))
            
            self.machine_data['verify_patched'] = 'OK'
            self._log(t('workflow.write_verified'), 'success')
            self.root.after(0, lambda: self._update_operation(100, t('op.verified')))
            self.root.after(800, self._hide_operation)
            
            self.root.after(0, lambda: self._set_instructions(
                t('workflow.bios_seq_instructions')
            ))
            self.root.after(0, lambda: self._set_action_btn(
                t('workflow.bios_seq_btn'), self.action_main, C['success']))
            self.current_step = 4
        except (FlashromError, Ch341progError) as e:
            self._log(t('err.write_failed', err=e), 'error')
            self.root.after(0, self._hide_operation)
            self.root.after(0, lambda: messagebox.showerror(
                t('err.write_failed_title'),
                t('err.write_failed_advice', err=e)))
            self.root.after(0, lambda: self.action_btn.config(state='normal'))
    
    # ════ STEP 5 ════════════════════════════════════════════════
    def step5_wait_bios_sequence(self):
        self._set_step(5, t('step.bios_sequence'))
        self._log(t('workflow.bios_seq_confirmed'), 'success')
        
        self.root.after(0, lambda: self._set_instructions(
            t('workflow.restore_ready_instructions')
        ))
        self.root.after(0, lambda: self._set_action_btn(
            t('workflow.restore_btn'), self.action_main, C['warning']))
        self.current_step = 5
        self.root.after(0, lambda: self.action_btn.config(state='normal'))
    
    # ════ STEP 6 ════════════════════════════════════════════════
    def step6_write_restore(self):
        self._set_step(6, t('step.restore'))
        self._log(t('workflow.restoring'), 'info')
        self._set_instructions(t('workflow.restoring_instructions'))
        self.root.after(0, lambda: self._show_operation(t('workflow.restore_op_title')))
        
        try:
            def on_progress_cb(percent, status):
                self.root.after(0, lambda p=percent, s=status: self._update_operation(p, s))
            
            # Ecriture du stock avec ch341prog
            self.ch341prog.write(
                self.machine_data['stock_path'],
                on_log=lambda l: self._log(f"  {l}", 'dim'),
                on_progress=on_progress_cb,
            )
            self._log(t('workflow.restore_done_verifying'), 'dim')
            
            # Verify : relit la puce et compare au stock
            self.root.after(0, lambda: self._update_operation(0, t('op.verification')))
            
            def on_verify_progress_cb(percent, status):
                vstatus = status.replace("Lecture :", "Verif :").replace("Read:", "Verify:")
                self.root.after(0, lambda p=percent, s=vstatus: self._update_operation(p, s))
            
            verify_ok = self.ch341prog.verify(
                self.machine_data['stock_path'],
                on_log=lambda l: self._log(f"  {l}", 'dim'),
                on_progress=on_verify_progress_cb,
            )
            
            if not verify_ok:
                raise Ch341progError(t('err.verify_failed_restore'))
            
            self.machine_data['verify_restore'] = 'OK'
            self._log(t('workflow.restore_done'), 'success')
            self.root.after(0, lambda: self._update_operation(100, t('op.verified')))
            self.root.after(800, self._hide_operation)
            
            self.root.after(0, lambda: self._set_step(7, t('step.done')))
            self.root.after(0, lambda: self._set_instructions(
                t('workflow.machine_done_instructions')
            ))
            self.root.after(0, lambda: self._set_action_btn(
                t('workflow.validate_btn'), self.action_main, C['success']))
            self.current_step = 6
        except (FlashromError, Ch341progError) as e:
            self._log(t('err.restore_failed', err=e), 'error')
            self.machine_data['verify_restore'] = 'FAIL'
            self.machine_data['notes'].append(f"restore failed: {e}")
            self.root.after(0, self._hide_operation)
            self.root.after(0, lambda: messagebox.showerror(
                t('err.restore_failed_title'),
                t('err.restore_failed_advice', err=e)))
            self.root.after(0, lambda: self.action_btn.config(state='normal'))
    
    # ════ STEP 7 ════════════════════════════════════════════════
    def step7_finalize(self):
        end_time = datetime.now()
        start = self.machine_data['start_time'] or end_time
        duration_min = round((end_time - start).total_seconds() / 60, 1)
        
        boot_ok = messagebox.askyesno(
            t('dialog.test_title'),
            t('dialog.test_prompt')
        )
        
        status = 'SUCCESS' if boot_ok else 'FAIL_BOOT'
        if not boot_ok:
            self.machine_data['notes'].append('boot test failed')
        
        chip = self.machine_data.get('chip') or {}
        
        self.logger.add_entry(
            SN=self.machine_data['sn'],
            MTM=self.machine_data['mtm'],
            BIOS_version=self.machine_data['bios_version'],
            Date=start.strftime('%Y-%m-%d'),
            Heure_debut=start.strftime('%H:%M:%S'),
            Heure_fin=end_time.strftime('%H:%M:%S'),
            Duree_min=duration_min,
            Stock_MD5=self.machine_data['stock_md5'],
            Patched_MD5=self.machine_data['patched_md5'],
            Chip_model=f"{chip.get('vendor','')} {chip.get('name','')}".strip(),
            Chip_size_kB=chip.get('size_kb', ''),
            Verify_patched=self.machine_data['verify_patched'],
            Verify_restore=self.machine_data['verify_restore'],
            Statut=status,
            Notes=' | '.join(self.machine_data['notes']),
        )
        
        self._log(f"📊 {self.machine_data['sn']} — {status} — {duration_min}min",
                  'success' if status == 'SUCCESS' else 'error')
        self._update_session_info()
        self._reset_machine()
    
    # ════ ACTIONS SECONDAIRES ═══════════════════════════════════
    def skip_machine(self):
        if self.current_step == 0:
            return
        if not messagebox.askyesno(t('session.skip_title'), t('session.skip_confirm')):
            return
        end_time = datetime.now()
        start = self.machine_data.get('start_time') or end_time
        duration_min = round((end_time - start).total_seconds() / 60, 1)
        chip = self.machine_data.get('chip') or {}
        
        self.logger.add_entry(
            SN=self.machine_data.get('sn') or 'UNKNOWN',
            MTM=self.machine_data.get('mtm', ''),
            BIOS_version=self.machine_data.get('bios_version', ''),
            Date=start.strftime('%Y-%m-%d'),
            Heure_debut=start.strftime('%H:%M:%S'),
            Heure_fin=end_time.strftime('%H:%M:%S'),
            Duree_min=duration_min,
            Stock_MD5=self.machine_data.get('stock_md5', ''),
            Patched_MD5=self.machine_data.get('patched_md5', ''),
            Chip_model=f"{chip.get('vendor','')} {chip.get('name','')}".strip(),
            Chip_size_kB=chip.get('size_kb', ''),
            Verify_patched=self.machine_data.get('verify_patched', ''),
            Verify_restore=self.machine_data.get('verify_restore', ''),
            Statut='ABORTED',
            Notes=f"aborted at step {self.current_step}",
        )
        self._log(f"⏭ Machine passée (step {self.current_step})", 'warning')
        self._update_session_info()
        self._reset_machine()
    
    def finish_session(self):
        summary = self.logger.session_summary()
        if summary['total'] == 0:
            if messagebox.askyesno(t('session.empty_title'), t('session.empty_msg')):
                self.root.destroy()
            return
        
        msg = t('session.end_msg',
                total=summary['total'],
                success=summary['success'],
                failed=summary['failed'],
                csv=summary['csv_path'])
        if messagebox.askyesno(t('session.end_title'), msg):
            self.root.destroy()


def main():
    # ─── Selection de la langue ───────────────────────────────
    # Priorite : 1) arg --lang=xx, 2) config.json, 3) selecteur GUI
    config_path = str(CONFIG_FILE)
    lang = detect_language_from_args()
    if lang is None:
        lang = load_language_from_config(config_path)
    if lang is None:
        # Premier lancement : afficher le selecteur
        from language_selector import show_language_selector
        lang = show_language_selector()
        save_language_to_config(config_path, lang)
    set_language(lang)
    
    # ─── Lancement de l'app principale ────────────────────────
    root = Tk()
    app = OperatorApp(root)
    
    def on_close():
        if app._log_fh:
            try:
                app._log_fh.write(f"# Session fermee : {datetime.now().isoformat()}\n")
                app._log_fh.close()
            except Exception:
                pass
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == '__main__':
    main()
