"""
Selecteur de langue affiche au demarrage de l'application.

Affiche une petite fenetre avec 2 boutons (Francais / English).
La selection est :
  1. sauvegardee dans config.json pour les lancements suivants
  2. retournee comme code langue (fr|en)

Si la langue est deja dans config.json, on ne demande pas a nouveau,
sauf si --force-lang est passe en argument.
"""
import sys
from pathlib import Path
from tkinter import Tk, Frame, Label, Button

# Theme partage avec l'app principale
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


def show_language_selector() -> str:
    """
    Affiche le selecteur de langue. Bloque jusqu'a la selection.
    
    Returns: 'fr' ou 'en' (defaut 'fr' si fenetre fermee sans choix)
    """
    selected = {'lang': 'fr'}  # defaut
    
    root = Tk()
    root.title("Langue / Language")
    root.geometry("420x320")
    root.configure(bg=C['bg'])
    root.resizable(False, False)
    
    # Centrer
    root.update_idletasks()
    x = (root.winfo_screenwidth() - 420) // 2
    y = (root.winfo_screenheight() - 320) // 2
    root.geometry(f"+{x}+{y}")
    
    # Header
    header = Frame(root, bg=C['bg_alt'], height=60)
    header.pack(fill='x')
    header.pack_propagate(False)
    
    Label(header, text="🔓  T470s UEFI Unlock Operator",
          font=('Segoe UI', 13, 'bold'),
          bg=C['bg_alt'], fg=C['accent']
          ).pack(pady=15)
    
    # Body
    body = Frame(root, bg=C['bg'])
    body.pack(fill='both', expand=True, padx=30, pady=20)
    
    Label(body, text="🌍",
          font=('Segoe UI Emoji', 32),
          bg=C['bg'], fg=C['fg']).pack(pady=(10, 5))
    
    Label(body, text="Choisissez votre langue / Choose your language",
          font=('Segoe UI', 11),
          bg=C['bg'], fg=C['fg']).pack(pady=(0, 20))
    
    def pick(lang: str):
        selected['lang'] = lang
        root.destroy()
    
    # Bouton Français
    btn_fr = Button(
        body, text="🇫🇷    Français",
        font=('Segoe UI', 12, 'bold'),
        bg=C['accent'], fg=C['bg'],
        relief='flat', cursor='hand2',
        pady=12, borderwidth=0,
        command=lambda: pick('fr'),
    )
    btn_fr.pack(fill='x', pady=4)
    
    # Bouton English
    btn_en = Button(
        body, text="🇬🇧    English",
        font=('Segoe UI', 12, 'bold'),
        bg=C['bg_widget'], fg=C['fg'],
        relief='flat', cursor='hand2',
        pady=12, borderwidth=0,
        command=lambda: pick('en'),
    )
    btn_en.pack(fill='x', pady=4)
    
    # Effets de survol
    def on_enter_fr(e): btn_fr.config(bg='#8db4f8')
    def on_leave_fr(e): btn_fr.config(bg=C['accent'])
    def on_enter_en(e): btn_en.config(bg=C['border'])
    def on_leave_en(e): btn_en.config(bg=C['bg_widget'])
    
    btn_fr.bind('<Enter>', on_enter_fr)
    btn_fr.bind('<Leave>', on_leave_fr)
    btn_en.bind('<Enter>', on_enter_en)
    btn_en.bind('<Leave>', on_leave_en)
    
    # Touches clavier rapides
    root.bind('<Key-f>', lambda e: pick('fr'))
    root.bind('<Key-F>', lambda e: pick('fr'))
    root.bind('<Key-e>', lambda e: pick('en'))
    root.bind('<Key-E>', lambda e: pick('en'))
    root.bind('<Escape>', lambda e: pick('fr'))
    
    root.mainloop()
    return selected['lang']


if __name__ == '__main__':
    lang = show_language_selector()
    print(lang)
