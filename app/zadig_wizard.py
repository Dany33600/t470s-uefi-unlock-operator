"""
Wizard pour installer le driver libusb du CH341A via Zadig.
Reutilisable depuis l'installeur et depuis l'app principale.
"""
import subprocess
from pathlib import Path
from tkinter import Toplevel, Frame, Label, Button, Text, messagebox
import tkinter as tk


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
    Retourne True si le lancement a reussi (= UAC accepte),
    False sinon.
    
    Note : on ne peut pas savoir ce que l'utilisateur fait
    DANS Zadig, seulement si Zadig s'est lance.
    """
    try:
        result = subprocess.run([
            'powershell', '-NoProfile', '-Command',
            f"Start-Process -FilePath '{zadig_path}' -Verb RunAs -Wait"
        ], capture_output=True, timeout=600,
           creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
        
        # -Wait fait attendre la fermeture de Zadig.
        # returncode 0 = Zadig lance et ferme normalement.
        # PowerShell echoue si UAC refuse.
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        # 10 min, l'utilisateur a fait trop longtemps ou oublie
        return False
    except Exception:
        return False


class ZadigWizard:
    """
    Fenetre modale qui guide l'utilisateur pour installer le driver
    libusb via Zadig. Lance Zadig en admin, attend la fermeture,
    appelle ensuite un callback de re-test.
    """
    
    def __init__(self, parent, on_retest_callback,
                 zadig_path: Path = None,
                 first_install: bool = False):
        """
        Args:
            parent: Toplevel parent
            on_retest_callback: fonction sans argument, appelee quand
                                l'utilisateur clique "Re-tester".
                                Doit retourner True si OK, False sinon.
            zadig_path: chemin vers zadig.exe (auto-detecte sinon)
            first_install: True si c'est l'install initiale,
                          False si c'est une re-config depuis l'app
        """
        self.parent = parent
        self.on_retest = on_retest_callback
        self.zadig_path = zadig_path or find_zadig_exe()
        self.first_install = first_install
        self.result = False  # True si driver finalement OK
        self._build_ui()
    
    def _build_ui(self):
        self.window = Toplevel(self.parent)
        self.window.title("Configuration du driver CH341A")
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
              text="🔌 Configuration du driver CH341A",
              font=('Segoe UI', 16, 'bold'),
              bg=C['bg'], fg=C['accent']
              ).pack(pady=(20, 5))
        
        subtitle = ("Premiere installation" if self.first_install
                    else "Le driver libusb n'est pas installe sur ce CH341A")
        Label(self.window, text=subtitle,
              font=('Segoe UI', 10),
              bg=C['bg'], fg=C['fg_dim']
              ).pack(pady=(0, 15))
        
        # Statut courant
        self.status_label = Label(
            self.window,
            text="⏳  Driver non configure",
            font=('Segoe UI', 11, 'bold'),
            bg=C['bg'], fg=C['warning']
        )
        self.status_label.pack(pady=(0, 15))
        
        # Instructions
        instr_frame = Frame(self.window, bg=C['bg_widget'])
        instr_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        instructions = (
            "📋  PROCEDURE\n"
            "\n"
            "1. Clique sur « Lancer Zadig » ci-dessous\n"
            "   → Windows demandera des droits administrateur, accepte\n"
            "\n"
            "2. Dans Zadig (qui s'ouvre) :\n"
            "\n"
            "   a) Menu  Options  →  coche « List All Devices »\n"
            "\n"
            "   b) Dans la liste deroulante du haut, selectionne :\n"
            "      « USB-EPP/I2C... CH341A »  (VID:PID = 1A86:5512)\n"
            "\n"
            "   c) A droite, dans la zone du driver, choisis « WinUSB »\n"
            "      (au lieu de CH341PAR)\n"
            "\n"
            "   d) Clique sur « Replace Driver »\n"
            "      → attends le message de succes (~15 sec)\n"
            "\n"
            "   e) Ferme Zadig (croix en haut a droite)\n"
            "\n"
            "3. Clique sur « J'ai termine » ci-dessous\n"
            "   → l'application va re-tester la detection\n"
            "\n"
            "⚠️  NeoProgrammer (si tu l'utilises) ne marchera plus avec\n"
            "    ce CH341A. Tu pourras revenir au driver d'origine via\n"
            "    Zadig (selectionne CH341PAR au lieu de WinUSB)."
        )
        
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
            btn_frame, text="🚀  Lancer Zadig (en admin)",
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
            sub_btns, text="✅  J'ai termine — Re-tester",
            command=self._retest,
            font=('Segoe UI', 10, 'bold'),
            bg=C['success'], fg=C['bg'],
            relief='flat', cursor='hand2', pady=8, borderwidth=0,
            activebackground=C['border'], activeforeground=C['fg'],
            state='disabled',
        )
        self.retest_btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
        
        Button(sub_btns, text="Annuler",
               command=self._cancel,
               font=('Segoe UI', 10),
               bg=C['bg_widget'], fg=C['fg_dim'],
               relief='flat', cursor='hand2', pady=8, borderwidth=0,
              ).pack(side='right', fill='x', expand=True, padx=(4, 0))
        
        # Si Zadig est introuvable, on l'indique
        if not self.zadig_path or not self.zadig_path.exists():
            self.zadig_btn.config(
                state='disabled',
                text="❌  zadig.exe introuvable dans tools/",
                bg=C['error'],
            )
    
    def _launch_zadig(self):
        """Lance Zadig en admin. Bloque jusqu'a sa fermeture, mais
        dans un thread separe pour ne pas figer l'UI Tk."""
        import threading
        
        self.zadig_btn.config(state='disabled', text="⏳  Zadig en cours...")
        self.status_label.config(
            text="🔧  Zadig est ouvert — fais le switch puis ferme-le",
            fg=C['accent']
        )
        self.window.update_idletasks()
        
        def _worker():
            launched = launch_zadig_admin(self.zadig_path)
            # Le callback UI doit etre fait dans le thread Tk principal
            self.window.after(0, lambda: self._zadig_finished(launched))
        
        threading.Thread(target=_worker, daemon=True).start()
    
    def _zadig_finished(self, launched: bool):
        """Appele dans le thread principal quand Zadig se ferme."""
        if launched:
            self.status_label.config(
                text="✅  Zadig ferme — clique sur « Re-tester »",
                fg=C['success']
            )
            self.retest_btn.config(state='normal')
            self.zadig_btn.config(state='normal',
                                   text="🔄  Relancer Zadig si besoin")
        else:
            self.status_label.config(
                text="⚠️  Zadig n'a pas pu etre lance (UAC refuse ?)",
                fg=C['error']
            )
            self.zadig_btn.config(state='normal',
                                   text="🚀  Relancer Zadig (en admin)")
    
    def _retest(self):
        """Re-teste la detection via le callback (dans un thread)."""
        import threading
        
        self.retest_btn.config(state='disabled', text="⏳  Test en cours...")
        self.status_label.config(text="🔍  Test de detection en cours...",
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
            self.status_label.config(text="✅  Driver OK — fermeture...",
                                      fg=C['success'])
            self.result = True
            self.window.after(1000, self._close)
        else:
            msg = "❌  Driver toujours pas detecte"
            if err:
                msg += f" — {err[:60]}"
            self.status_label.config(text=msg, fg=C['error'])
            self.retest_btn.config(state='normal',
                                    text="✅  J'ai termine — Re-tester")
    
    def _cancel(self):
        self.result = False
        self._close()
    
    def _close(self):
        self.window.grab_release()
        self.window.destroy()
    
    def wait(self) -> bool:
        """Bloque jusqu'a la fermeture de la fenetre. Retourne True
        si le driver a finalement ete configure avec succes."""
        self.parent.wait_window(self.window)
        return self.result
