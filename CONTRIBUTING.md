# Contributing — T470s UEFI Unlock Operator

🇫🇷 [Français](#français) — 🇬🇧 [English](#english)

---

## Français

Merci de votre intérêt pour ce projet !

### 🐛 Signaler un bug

Ouvrez une [Issue](https://github.com/Dany33600/t470s-uefi-unlock-operator/issues/new)
en incluant :
- Le **modèle exact** du laptop (T470s, T480, X1 Carbon...)
- La **puce SPI détectée** (visible dans l'app)
- Le **log de session** (dans `logs/session_*.log`)
- Une **capture d'écran** si possible

### 💡 Proposer une fonctionnalité

Ouvrez une Issue avec le label `enhancement`. Décrivez :
- Le besoin (quel problème ça résout)
- Le comportement attendu

### 🔧 Soumettre du code

1. Forkez le repo
2. Créez une branche : `git checkout -b feature/ma-feature`
3. Codez, testez (idéalement sur du matériel réel — sinon notez-le dans la PR)
4. Committez avec un message clair : `git commit -m "Add support for T480"`
5. Pushez : `git push origin feature/ma-feature`
6. Ouvrez une [Pull Request](https://github.com/Dany33600/t470s-uefi-unlock-operator/pulls)

### 🌍 Ajouter une langue

Le système d'i18n est dans `app/i18n.py`. Pour ajouter une langue :
1. Dupliquez le dict `'fr'` en `'es'` (par exemple)
2. Traduisez les valeurs
3. Ajoutez le bouton dans `app/language_selector.py`
4. Ajoutez aussi les traductions dans `installer/installer.py` (mini dict
   séparé)

### 📐 Style de code

- Python 3.8+ compatible
- `snake_case` pour fonctions/variables, `PascalCase` pour classes
- Pas de dépendance pip nouvelle sans justification (tout doit marcher
  uniquement avec la stdlib)
- Commentaires en français ou anglais, peu importe, du moment qu'ils sont
  clairs

---

## English

Thanks for your interest in this project!

### 🐛 Report a bug

Open an [Issue](https://github.com/Dany33600/t470s-uefi-unlock-operator/issues/new)
including:
- The **exact laptop model** (T470s, T480, X1 Carbon...)
- The **detected SPI chip** (shown in the app)
- The **session log** (in `logs/session_*.log`)
- A **screenshot** if possible

### 💡 Suggest a feature

Open an Issue with the `enhancement` label. Describe:
- The need (what problem it solves)
- The expected behavior

### 🔧 Submit code

1. Fork the repo
2. Create a branch: `git checkout -b feature/my-feature`
3. Code, test (ideally on real hardware — otherwise note it in the PR)
4. Commit with a clear message: `git commit -m "Add support for T480"`
5. Push: `git push origin feature/my-feature`
6. Open a [Pull Request](https://github.com/Dany33600/t470s-uefi-unlock-operator/pulls)

### 🌍 Add a language

The i18n system is in `app/i18n.py`. To add a language:
1. Duplicate the `'fr'` dict to `'es'` (for example)
2. Translate the values
3. Add the button in `app/language_selector.py`
4. Also add translations to `installer/installer.py` (separate mini dict)

### 📐 Code style

- Python 3.8+ compatible
- `snake_case` for functions/variables, `PascalCase` for classes
- No new pip dependency without justification (everything must work using
  only the stdlib)
- Comments in French or English, either is fine, as long as they are clear
