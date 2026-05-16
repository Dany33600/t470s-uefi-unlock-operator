"""
Wizard pour installer le driver libusb du CH341A via Zadig.
Reutilisable depuis l'installeur et depuis l'app principale.
Internationalise (FR/EN) via le module i18n.
"""
import subprocess
from pathlib import Path
from tkinter import Toplevel, Frame, Label, Button, Text, messagebox
import tkinter as tk

from i18n import t


# Couleurs (dark theme — doit etre coherent avec le reste de l'app)
C = {
    'bg':        '#1a1b26',
    'bg_alt':    '#24283b',
    'bg_widget': '#2f334d',
    'fg':        '#c0caf5',
    'fg_dim':    '#a9b1d6',
    'accent':    '#7aa2f7',
    'success':   '#9ece6a',
    'warning':   '#e0af68',
    'error':     '#f7768e',
    'border':    '#414868',
}


def find_zadig_exe(root_dir: Path = None) -> Path:
    """Trouve zadig.exe dans le projet. None si introuvable."""
    if root_dir is None:
        root_dir = Path(__file__).resolve().parent.parent
    
    candidates = [
        root_dir / 'tools' / 'zadig.exe',
        root_dir / 'tools' / 'zadig-2.9.exe',
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def launch_zadig_admin(zadig_path: Path) -> bool:
    """
    Lance Zadig avec elevation administrateur via PowerShell.
    Retourne True si le lancement a reussi (= UAC accepte), False sinon.
    """
    try:
        result = subprocess.run([
            'powershell', '-NoProfile', '-Command',
            f"Start-Process -FilePath '{zadig_path}' -Verb RunAs -Wait"
        ], capture_output=True, timeout=600,
           creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


class ZadigWizard:
    """
    Fenetre modale qui guide l'utilisateur pour installer le driver
    libusb via Zadig.
    """
    
    def __init__(self, parent, on_retest_callback,
                 zadig_path: Path = None,
                 first_install: bool = False):
        self.parent = parent
        self.on_retest = on_retest_callback
        self.zadig_path = zadig_path or find_zadig_exe()
        self.first_install = first_install
        self.result = False
        self._build_ui()
    
    def _build_ui(self):
        self.window = Toplevel(self.parent)
        self.window.title(t('zadig.title'))
        self.window.geometry("720x620")
        self.window.configure(bg=C['bg'])
        self.window.transient(self.parent)
        self.window.grab_set()
        
        # Centrer la fenetre
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 720) // 2
        y = (self.window.winfo_screenheight() - 620) // 2
        self.window.geometry(f"+{x}+{y}")
        
        # Header
        Label(self.window,
              text=t('zadig.header'),
              font=('Segoe UI', 16, 'bold'),
              bg=C['bg'], fg=C['accent']
              ).pack(pady=(20, 5))
        
        Label(self.window, text=t('zadig.subtitle'),
              font=('Segoe UI', 10),
              bg=C['bg'], fg=C['fg_dim']
              ).pack(pady=(0, 15))
        
        # Statut courant
        self.status_label = Label(
            self.window,
            text=t('zadig.status_not_configured'),
            font=('Segoe UI', 11, 'bold'),
            bg=C['bg'], fg=C['warning']
        )
        self.status_label.pack(pady=(0, 15))
        
        # Instructions (recuperees depuis i18n)
        instr_frame = Frame(self.window, bg=C['bg_widget'])
        instr_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        instructions = t('zadig.procedure_title') + "\n\n" + t('zadig.procedure')
        
        text_widget = Text(instr_frame, wrap='word',
                            bg=C['bg_widget'], fg=C['fg'],
                            font=('Segoe UI', 10),
                            relief='flat', padx=15, pady=10,
                            height=22)
        text_widget.pack(fill='both', expand=True)
        text_widget.insert('1.0', instructions)
        text_widget.config(state='disabled')
        
        # Boutons
        btn_frame = Frame(self.window, bg=C['bg'])
        btn_frame.pack(fill='x', padx=20, pady=15)
        
        self.zadig_btn = Button(
            btn_frame, text=t('zadig.launch_btn'),
            command=self._launch_zadig,
            font=('Segoe UI', 11, 'bold'),
            bg=C['accent'], fg=C['bg'],
            relief='flat', cursor='hand2', pady=10, borderwidth=0,
            activebackground=C['border'], activeforeground=C['fg'],
        )
        self.zadig_btn.pack(fill='x', pady=(0, 8))
        
        sub_btns = Frame(btn_frame, bg=C['bg'])
        sub_btns.pack(fill='x')
        
        self.retest_btn = Button(
            sub_btns, text=t('zadig.done_btn'),
            command=self._retest,
            font=('Segoe UI', 10, 'bold'),
            bg=C['success'], fg=C['bg'],
            relief='flat', cursor='hand2', pady=8, borderwidth=0,
            activebackground=C['border'], activeforeground=C['fg'],
            state='disabled',
        )
        self.retest_btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
        
        Button(sub_btns, text=t('zadig.cancel_btn'),
               command=self._cancel,
               font=('Segoe UI', 10),
               bg=C['bg_widget'], fg=C['fg_dim'],
               relief='flat', cursor='hand2', pady=8, borderwidth=0,
              ).pack(side='right', fill='x', expand=True, padx=(4, 0))
        
        # Si Zadig est introuvable, on l'indique
        if not self.zadig_path or not self.zadig_path.exists():
            self.zadig_btn.config(
                state='disabled',
                text=t('zadig.not_found_title'),
                bg=C['error'],
            )
    
    def _launch_zadig(self):
        """Lance Zadig en admin dans un thread separe."""
        import threading
        
        self.zadig_btn.config(state='disabled', text="⏳  Zadig...")
        self.status_label.config(
            text="🔧  " + t('zadig.status_testing').replace(t('zadig.status_testing'),
                  t('zadig.status_testing')),
            fg=C['accent']
        )
        # On affiche un message clair pendant l'attente
        self.status_label.config(text="🔧  Zadig", fg=C['accent'])
        self.window.update_idletasks()
        
        def _worker():
            launched = launch_zadig_admin(self.zadig_path)
            self.window.after(0, lambda: self._zadig_finished(launched))
        
        threading.Thread(target=_worker, daemon=True).start()
    
    def _zadig_finished(self, launched: bool):
        """Appele dans le thread principal quand Zadig se ferme."""
        if launched:
            self.status_label.config(
                text=t('zadig.status_ok'),
                fg=C['success']
            )
            self.retest_btn.config(state='normal')
            self.zadig_btn.config(state='normal',
                                   text=t('zadig.launch_btn'))
        else:
            self.status_label.config(
                text=t('zadig.status_fail'),
                fg=C['error']
            )
            self.zadig_btn.config(state='normal',
                                   text=t('zadig.launch_btn'))
    
    def _retest(self):
        """Re-teste la detection via le callback (dans un thread)."""
        import threading
        
        self.retest_btn.config(state='disabled', text=t('zadig.status_testing'))
        self.status_label.config(text=t('zadig.retesting'),
                                  fg=C['accent'])
        self.window.update_idletasks()
        
        def _worker():
            try:
                ok = self.on_retest()
                err = None
            except Exception as e:
                ok = False
                err = str(e)
            self.window.after(0, lambda: self._retest_finished(ok, err))
        
        threading.Thread(target=_worker, daemon=True).start()
    
    def _retest_finished(self, ok: bool, err: str = None):
        """Appele dans le thread principal apres le re-test."""
        if ok:
            self.status_label.config(text=t('zadig.test_ok'),
                                      fg=C['success'])
            self.result = True
            self.window.after(1000, self._close)
        else:
            msg = t('zadig.test_fail')
            if err:
                msg += f"\n{err[:80]}"
            self.status_label.config(text=msg, fg=C['error'])
            self.retest_btn.config(state='normal',
                                    text=t('zadig.done_btn'))
    
    def _cancel(self):
        self.result = False
        self._close()
    
    def _close(self):
        self.window.grab_release()
        self.window.destroy()
    
    def wait(self) -> bool:
        """Bloque jusqu'a la fermeture de la fenetre."""
        self.parent.wait_window(self.window)
        return self.result
