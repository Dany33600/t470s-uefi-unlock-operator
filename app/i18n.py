"""
i18n — Gestion des langues de l'application.

Deux langues supportees :
- fr (français)
- en (anglais)

Usage :
    from i18n import t, set_language
    set_language('en')
    print(t('app.title'))  # "T470s UEFI Unlock Operator"
    print(t('step.detect'))  # "Detection of CH341A + chip"

La langue est selectionnee au lancement (start.bat) via un argument
--lang=fr ou --lang=en, ou bien stockee dans config.json.
"""
import json
from pathlib import Path
from typing import Optional


# ─── Dictionnaires de traduction ───────────────────────────────
TRANSLATIONS = {
    'fr': {
        # ═══ Generique ═══════════════════════════════════════
        'app.title': 'T470s UEFI Unlock Operator',
        'app.session_started': '✨ Session démarrée. CSV : {path}',
        'app.log_file': '📝 Fichier de log : {path}',
        
        'btn.confirm': 'Confirmer',
        'btn.cancel': 'Annuler',
        'btn.retry': 'Réessayer',
        'btn.close': 'Fermer',
        'btn.continue': 'Continuer',
        'btn.skip_machine': 'Passer cette machine',
        'btn.end_session': 'Terminer la session',
        
        # ═══ Headers UI ═══════════════════════════════════════
        'ui.machines_count': 'Machines : {n}',
        'ui.session_file': 'Session : {file}',
        'ui.workflow': 'Workflow',
        'ui.console': 'Console',
        'ui.instructions': 'Instructions',
        'ui.machine_current': 'Machine en cours',
        'ui.machine_none': '(aucune machine commencée)',
        'ui.step_n_of_total': 'Étape {n}/7 — {title}',
        
        # ═══ Steps (titres) ═══════════════════════════════════
        'step.detect': 'Détection CH341A + puce',
        'step.read': 'Lecture (dump stock)',
        'step.patch': 'Patch du firmware',
        'step.write_patched': 'Écriture PATCHED',
        'step.bios_sequence': 'Séquence BIOS effectuée',
        'step.restore': 'Restauration stock',
        'step.done': 'Terminé !',
        
        # ═══ Workflow messages ═══════════════════════════════
        'workflow.ready_title': 'Étape 1/7 — Prêt',
        'workflow.ready_instructions': (
            "Branchez le clip SOIC-8 sur la puce EEPROM du ThinkPad.\n\n"
            "Rappels :\n"
            "• Les 2 batteries (principale + CMOS) doivent être débranchées\n"
            "• Ligne rouge du clip alignée avec le point sur la puce\n"
            "• CH341A connecté en USB sur ce PC\n\n"
            "Quand vous êtes prêt, cliquez sur ▶ Démarrer."
        ),
        'workflow.start_machine': '▶  Démarrer cette machine',
        
        'workflow.detecting': '🔍 Détection du CH341A et de la puce SPI...',
        'workflow.detecting_instructions': 'Détection en cours, ne touchez à rien.',
        'workflow.chip_detected': '✅ {vendor} {name} détectée ({size} kB)',
        'workflow.chip_detected_instructions': (
            "Puce détectée : {vendor} {name}\n\n"
            "Prêt à dumper le contenu (~4 min pour 16 Mo).\n\n"
            "Cliquez sur 'Lire la puce'."
        ),
        'workflow.read_chip_btn': '📥  Lire la puce (stock)',
        
        'workflow.reading': '📥 Lecture de la puce...',
        'workflow.reading_instructions': 'Lecture en cours. ~4 minutes.',
        'workflow.read_op_title': '📥  Lecture de la puce',
        'workflow.read_done': '✅ Lecture terminée',
        'workflow.read_status_mb': 'Lecture : {mb:.1f} Mo  •  ETA : {eta}s',
        
        'workflow.analyzing': '🔍 Analyse du dump...',
        'workflow.sn_detected': '  SN détecté     : {sn} (confiance : {conf})',
        'workflow.mtm_detected': '  MTM            : {mtm}',
        'workflow.bios_detected': '  Version BIOS   : {bios}',
        'workflow.md5_stock': '  MD5 stock      : {md5}',
        'workflow.saved_at': '  Sauvegardé     : {path}',
        
        'workflow.dump_saved_instructions': (
            "Dump sauvegardé pour {sn}.\n\n"
            "Prochaine étape : générer le firmware patché (~10s)."
        ),
        'workflow.patch_btn': '⚙  Patcher le dump',
        
        'workflow.patching': '⚙ Application du patch UEFI...',
        'workflow.patching_instructions': 'Patch en cours, quelques secondes.',
        'workflow.patch_op_title': '⚙  Patch du firmware',
        'workflow.patch_status': 'Application du patch',
        'workflow.patch_done': '✅ Patched généré : {file}',
        'workflow.md5_patched': '  MD5 patched    : {md5}',
        
        'workflow.patched_ready_instructions': (
            "Patch généré.\n\n"
            "⚠️ ÉCRITURE du firmware patché (~5 min).\n"
            "Ne touchez surtout pas au clip."
        ),
        'workflow.write_patched_btn': '📤  Écrire le PATCHED',
        
        'workflow.writing_patched': '📤 Écriture du firmware patché...',
        'workflow.writing_instructions': 'ÉCRITURE EN COURS — NE TOUCHEZ À RIEN (~5 min).',
        'workflow.write_op_title': '📤  Écriture du firmware patché',
        'workflow.write_status_mb': 'Écriture : {mb:.1f} Mo  •  ETA : {eta}s',
        'workflow.write_done_verifying': '  Écriture terminée, vérification...',
        'workflow.verify_status_mb': 'Vérif : {mb:.1f} Mo  •  ETA : {eta}s',
        'workflow.write_verified': '✅ Écriture VERIFIED',
        
        'workflow.bios_seq_instructions': (
            "🔧 INTERVENTION MANUELLE\n\n"
            "1. Débranchez le clip (laissez côté CH341A)\n"
            "2. Rebranchez la batterie principale du ThinkPad\n"
            "3. Allumez → logo Lenovo + bips → F1\n"
            "4. Password : n'importe quoi → Entrée\n"
            "5. Hardware ID : Entrée (vide)\n"
            "6. Espace 2 fois\n"
            "7. Éteignez, débranchez la batterie\n"
            "8. Re-clip sur la puce\n\n"
            "Cliquez sur 'OK séquence faite'."
        ),
        'workflow.bios_seq_btn': '✅  OK, séquence BIOS faite',
        'workflow.bios_seq_confirmed': '✅ Séquence BIOS confirmée',
        
        'workflow.restore_ready_instructions': (
            "Clip rebranché sur la puce ?\n\n"
            "Prochaine étape : restaurer le firmware d'origine.\n"
            "⚠️ Écriture du STOCK sauvegardé (~5 min)."
        ),
        'workflow.restore_btn': '🔁  Restaurer le firmware stock',
        
        'workflow.restoring': "🔁 Écriture du firmware stock d'origine...",
        'workflow.restoring_instructions': 'RESTAURATION EN COURS (~5 min).',
        'workflow.restore_op_title': '🔁  Restauration du firmware stock',
        'workflow.restore_done_verifying': '  Restauration écrite, vérification...',
        'workflow.restore_done': '✅ Firmware stock restauré',
        
        'workflow.machine_done_instructions': (
            "✅ MACHINE TERMINÉE\n\n"
            "1. Débranchez le clip\n"
            "2. Rebranchez les 2 batteries (CMOS + principale)\n"
            "3. Revissez le fond\n"
            "4. Testez le boot — BIOS sans password ?\n\n"
            "Cliquez sur Valider quand testé."
        ),
        'workflow.validate_btn': '🏁  Valider et machine suivante',
        
        # ═══ Erreurs ══════════════════════════════════════════
        'err.read_failed': '❌ Lecture échouée : {err}',
        'err.read_failed_title': 'Lecture échouée',
        'err.write_failed': '❌ Écriture échouée : {err}',
        'err.write_failed_title': 'Écriture échouée',
        'err.write_failed_advice': '{err}\n\n⚠️ Re-vérifiez le clip puis recommencez.',
        'err.restore_failed': '❌ Restauration échouée : {err}',
        'err.restore_failed_title': 'Restauration échouée',
        'err.restore_failed_advice': "{err}\n\n⚠️ Le firmware n'est PAS restauré.",
        'err.patch_failed': '❌ Patch échoué : {err}',
        'err.patch_failed_title': 'Patch échoué',
        'err.detect_failed_title': 'Détection échouée',
        'err.driver_not_installed_warn': '⚠️ Driver libusb non installé — wizard Zadig ouvert',
        'err.aborted_by_user': "⏭ Annulation par l'utilisateur",
        'err.verify_failed_patched': (
            "Vérification échouée : la puce ne contient pas exactement les "
            "mêmes données que le fichier patché.\n"
            "Re-vérifiez le clip et recommencez."
        ),
        'err.verify_failed_restore': (
            "Vérification échouée : la puce ne correspond pas au firmware "
            "stock attendu. La machine PEUT ne pas booter."
        ),
        
        # ═══ Dialog SN ═══════════════════════════════════════
        'dialog.sn_title': 'Confirmation du Serial Number',
        'dialog.sn_header': '🔍  Vérification du Serial Number',
        'dialog.sn_confidence_high': '✅  Confiance élevée',
        'dialog.sn_confidence_medium': '⚠️  Confiance moyenne',
        'dialog.sn_confidence_low': '⚠️  Confiance faible',
        'dialog.sn_confidence_none': '❌  Non détecté',
        'dialog.sn_mtm_label': 'MTM détecté :',
        'dialog.sn_bios_label': 'Version BIOS :',
        'dialog.sn_unknown': 'inconnu',
        'dialog.sn_prompt': (
            "Vérifiez le SN sur l'étiquette sous le laptop\n"
            "et corrigez ci-dessous si nécessaire :"
        ),
        'dialog.sn_hint': '(format typique : PC0XXXXX, PF0XXXXX, R9XXXXXX...)',
        'dialog.sn_confirm_btn': '✅  Confirmer ce SN',
        'dialog.sn_empty_warn_title': 'SN vide',
        'dialog.sn_empty_warn': 'Entrez un SN valide.',
        'dialog.sn_invalid_warn_title': 'SN invalide',
        'dialog.sn_invalid_warn': 'Le SN ne doit contenir que des lettres et chiffres.',
        'dialog.sn_corrected_note': 'SN corrigé par utilisateur : {sn}',
        
        # ═══ Test final ═══════════════════════════════════════
        'dialog.test_title': 'Test final',
        'dialog.test_prompt': (
            "Le ThinkPad démarre sans password ?\n\n"
            "(Oui = SUCCESS, Non = FAIL)"
        ),
        
        # ═══ Fin de session ═══════════════════════════════════
        'session.empty_title': 'Session vide',
        'session.empty_msg': 'Aucune machine traitée. Fermer ?',
        'session.end_title': 'Terminer',
        'session.skip_title': 'Passer la machine',
        'session.skip_confirm': 'Annuler et logger comme ABORTED ?',
        'session.skipped_log': '⏭ Machine passée (étape {step})',
        'session.end_msg': (
            "Session terminée.\n\n"
            "  Total : {total}\n"
            "  ✅ Succès : {success}\n"
            "  ❌ Échecs : {failed}\n\n"
            "CSV :\n{csv}\n\nFermer ?"
        ),
        
        # ═══ Machine en cours ═════════════════════════════════
        'machine.sn': 'SN',
        'machine.mtm': 'MTM',
        'machine.bios': 'BIOS',
        'machine.chip': 'Chip',
        'machine.md5_stock': 'Stock MD5',
        
        # ═══ Operation panel ══════════════════════════════════
        'op.initializing': 'Initialisation...',
        'op.calculating': 'calcul...',
        'op.elapsed_eta': '{status}  •  {elapsed} écoulé  •  {eta} restant',
        'op.elapsed': '{elapsed} écoulé  •  {eta} restant',
        'op.eta_label': '~{mins:02d}:{secs:02d} restant',
        'op.finished': 'Terminé',
        'op.verified': 'VERIFIED',
        'op.verification': 'Vérification',
    },
    
    'en': {
        # ═══ Generic ══════════════════════════════════════════
        'app.title': 'T470s UEFI Unlock Operator',
        'app.session_started': '✨ Session started. CSV: {path}',
        'app.log_file': '📝 Log file: {path}',
        
        'btn.confirm': 'Confirm',
        'btn.cancel': 'Cancel',
        'btn.retry': 'Retry',
        'btn.close': 'Close',
        'btn.continue': 'Continue',
        'btn.skip_machine': 'Skip this machine',
        'btn.end_session': 'End session',
        
        # ═══ UI Headers ═══════════════════════════════════════
        'ui.machines_count': 'Machines: {n}',
        'ui.session_file': 'Session: {file}',
        'ui.workflow': 'Workflow',
        'ui.console': 'Console',
        'ui.instructions': 'Instructions',
        'ui.machine_current': 'Current machine',
        'ui.machine_none': '(no machine started)',
        'ui.step_n_of_total': 'Step {n}/7 — {title}',
        
        # ═══ Steps (titles) ═══════════════════════════════════
        'step.detect': 'CH341A + chip detection',
        'step.read': 'Read (stock dump)',
        'step.patch': 'Firmware patching',
        'step.write_patched': 'Write PATCHED',
        'step.bios_sequence': 'BIOS sequence done',
        'step.restore': 'Stock restoration',
        'step.done': 'Done!',
        
        # ═══ Workflow messages ═══════════════════════════════
        'workflow.ready_title': 'Step 1/7 — Ready',
        'workflow.ready_instructions': (
            "Attach the SOIC-8 clip to the ThinkPad's EEPROM chip.\n\n"
            "Reminders:\n"
            "• Both batteries (main + CMOS) must be disconnected\n"
            "• Red wire of the clip aligned with the dot on the chip\n"
            "• CH341A plugged into this PC via USB\n\n"
            "When ready, click ▶ Start."
        ),
        'workflow.start_machine': '▶  Start this machine',
        
        'workflow.detecting': '🔍 Detecting CH341A and SPI chip...',
        'workflow.detecting_instructions': "Detection in progress, don't touch anything.",
        'workflow.chip_detected': '✅ {vendor} {name} detected ({size} kB)',
        'workflow.chip_detected_instructions': (
            "Chip detected: {vendor} {name}\n\n"
            "Ready to dump contents (~4 min for 16 MB).\n\n"
            "Click 'Read chip'."
        ),
        'workflow.read_chip_btn': '📥  Read chip (stock)',
        
        'workflow.reading': '📥 Reading chip...',
        'workflow.reading_instructions': 'Read in progress. ~4 minutes.',
        'workflow.read_op_title': '📥  Reading chip',
        'workflow.read_done': '✅ Read complete',
        'workflow.read_status_mb': 'Read: {mb:.1f} MB  •  ETA: {eta}s',
        
        'workflow.analyzing': '🔍 Analyzing dump...',
        'workflow.sn_detected': '  SN detected    : {sn} (confidence: {conf})',
        'workflow.mtm_detected': '  MTM            : {mtm}',
        'workflow.bios_detected': '  BIOS version   : {bios}',
        'workflow.md5_stock': '  Stock MD5      : {md5}',
        'workflow.saved_at': '  Saved at       : {path}',
        
        'workflow.dump_saved_instructions': (
            "Dump saved for {sn}.\n\n"
            "Next step: generate the patched firmware (~10s)."
        ),
        'workflow.patch_btn': '⚙  Patch the dump',
        
        'workflow.patching': '⚙ Applying UEFI patch...',
        'workflow.patching_instructions': 'Patching in progress, a few seconds.',
        'workflow.patch_op_title': '⚙  Firmware patching',
        'workflow.patch_status': 'Applying patch',
        'workflow.patch_done': '✅ Patched file generated: {file}',
        'workflow.md5_patched': '  Patched MD5    : {md5}',
        
        'workflow.patched_ready_instructions': (
            "Patch generated.\n\n"
            "⚠️ WRITING the patched firmware (~5 min).\n"
            "Do NOT touch the clip."
        ),
        'workflow.write_patched_btn': '📤  Write PATCHED',
        
        'workflow.writing_patched': '📤 Writing patched firmware...',
        'workflow.writing_instructions': "WRITING IN PROGRESS — DON'T TOUCH ANYTHING (~5 min).",
        'workflow.write_op_title': '📤  Writing patched firmware',
        'workflow.write_status_mb': 'Write: {mb:.1f} MB  •  ETA: {eta}s',
        'workflow.write_done_verifying': '  Write complete, verifying...',
        'workflow.verify_status_mb': 'Verify: {mb:.1f} MB  •  ETA: {eta}s',
        'workflow.write_verified': '✅ Write VERIFIED',
        
        'workflow.bios_seq_instructions': (
            "🔧 MANUAL ACTION\n\n"
            "1. Unplug the clip (leave it on the CH341A side)\n"
            "2. Reconnect the ThinkPad's main battery\n"
            "3. Power on → Lenovo logo + beeps → F1\n"
            "4. Password: anything → Enter\n"
            "5. Hardware ID: Enter (empty)\n"
            "6. Space twice\n"
            "7. Shut down, disconnect battery\n"
            "8. Re-clip on the chip\n\n"
            "Click 'OK sequence done'."
        ),
        'workflow.bios_seq_btn': '✅  OK, BIOS sequence done',
        'workflow.bios_seq_confirmed': '✅ BIOS sequence confirmed',
        
        'workflow.restore_ready_instructions': (
            "Clip back on the chip?\n\n"
            "Next step: restore the original firmware.\n"
            "⚠️ Writing the saved STOCK (~5 min)."
        ),
        'workflow.restore_btn': '🔁  Restore stock firmware',
        
        'workflow.restoring': '🔁 Writing original stock firmware...',
        'workflow.restoring_instructions': 'RESTORATION IN PROGRESS (~5 min).',
        'workflow.restore_op_title': '🔁  Restoring stock firmware',
        'workflow.restore_done_verifying': '  Restore written, verifying...',
        'workflow.restore_done': '✅ Stock firmware restored',
        
        'workflow.machine_done_instructions': (
            "✅ MACHINE DONE\n\n"
            "1. Unplug the clip\n"
            "2. Reconnect both batteries (CMOS + main)\n"
            "3. Screw back the bottom cover\n"
            "4. Test the boot — BIOS without password?\n\n"
            "Click Validate once tested."
        ),
        'workflow.validate_btn': '🏁  Validate and next machine',
        
        # ═══ Errors ═══════════════════════════════════════════
        'err.read_failed': '❌ Read failed: {err}',
        'err.read_failed_title': 'Read failed',
        'err.write_failed': '❌ Write failed: {err}',
        'err.write_failed_title': 'Write failed',
        'err.write_failed_advice': '{err}\n\n⚠️ Re-check the clip and try again.',
        'err.restore_failed': '❌ Restore failed: {err}',
        'err.restore_failed_title': 'Restore failed',
        'err.restore_failed_advice': "{err}\n\n⚠️ The firmware is NOT restored.",
        'err.patch_failed': '❌ Patch failed: {err}',
        'err.patch_failed_title': 'Patch failed',
        'err.detect_failed_title': 'Detection failed',
        'err.driver_not_installed_warn': '⚠️ libusb driver not installed — Zadig wizard opening',
        'err.aborted_by_user': '⏭ Cancelled by user',
        'err.verify_failed_patched': (
            "Verification failed: the chip does not contain exactly the same "
            "data as the patched file.\n"
            "Re-check the clip and try again."
        ),
        'err.verify_failed_restore': (
            "Verification failed: the chip does not match the expected stock "
            "firmware. The machine MAY fail to boot."
        ),
        
        # ═══ SN Dialog ════════════════════════════════════════
        'dialog.sn_title': 'Serial Number confirmation',
        'dialog.sn_header': '🔍  Verify the Serial Number',
        'dialog.sn_confidence_high': '✅  High confidence',
        'dialog.sn_confidence_medium': '⚠️  Medium confidence',
        'dialog.sn_confidence_low': '⚠️  Low confidence',
        'dialog.sn_confidence_none': '❌  Not detected',
        'dialog.sn_mtm_label': 'MTM detected:',
        'dialog.sn_bios_label': 'BIOS version:',
        'dialog.sn_unknown': 'unknown',
        'dialog.sn_prompt': (
            "Check the SN on the sticker under the laptop\n"
            "and correct below if needed:"
        ),
        'dialog.sn_hint': '(typical format: PC0XXXXX, PF0XXXXX, R9XXXXXX...)',
        'dialog.sn_confirm_btn': '✅  Confirm this SN',
        'dialog.sn_empty_warn_title': 'Empty SN',
        'dialog.sn_empty_warn': 'Enter a valid SN.',
        'dialog.sn_invalid_warn_title': 'Invalid SN',
        'dialog.sn_invalid_warn': 'The SN must contain only letters and digits.',
        'dialog.sn_corrected_note': 'SN corrected by user: {sn}',
        
        # ═══ Final test ═══════════════════════════════════════
        'dialog.test_title': 'Final test',
        'dialog.test_prompt': (
            "Does the ThinkPad boot without a password?\n\n"
            "(Yes = SUCCESS, No = FAIL)"
        ),
        
        # ═══ Session end ══════════════════════════════════════
        'session.empty_title': 'Empty session',
        'session.empty_msg': 'No machine processed. Close?',
        'session.end_title': 'End session',
        'session.skip_title': 'Skip machine',
        'session.skip_confirm': 'Abort and log as ABORTED?',
        'session.skipped_log': '⏭ Machine skipped (step {step})',
        'session.end_msg': (
            "Session ended.\n\n"
            "  Total: {total}\n"
            "  ✅ Success: {success}\n"
            "  ❌ Failed: {failed}\n\n"
            "CSV:\n{csv}\n\nClose?"
        ),
        
        # ═══ Machine panel ════════════════════════════════════
        'machine.sn': 'SN',
        'machine.mtm': 'MTM',
        'machine.bios': 'BIOS',
        'machine.chip': 'Chip',
        'machine.md5_stock': 'Stock MD5',
        
        # ═══ Operation panel ══════════════════════════════════
        'op.initializing': 'Initializing...',
        'op.calculating': 'calculating...',
        'op.elapsed_eta': '{status}  •  {elapsed} elapsed  •  {eta} remaining',
        'op.elapsed': '{elapsed} elapsed  •  {eta} remaining',
        'op.eta_label': '~{mins:02d}:{secs:02d} remaining',
        'op.finished': 'Done',
        'op.verified': 'VERIFIED',
        'op.verification': 'Verification',
    },
}


# ─── Etat global de la langue ──────────────────────────────────
_current_lang = 'fr'  # defaut


def set_language(lang: str) -> None:
    """Change la langue courante. Si lang inconnue, garde la precedente."""
    global _current_lang
    if lang in TRANSLATIONS:
        _current_lang = lang


def get_language() -> str:
    """Retourne le code langue courant."""
    return _current_lang


def t(key: str, **kwargs) -> str:
    """
    Traduit une clé. Si la cle n'existe pas dans la langue courante,
    fallback sur le français, puis sur la cle elle-meme.
    
    Les kwargs sont passes a .format() pour les interpolations.
    """
    txt = TRANSLATIONS.get(_current_lang, {}).get(key)
    if txt is None:
        txt = TRANSLATIONS['fr'].get(key, key)
    if kwargs:
        try:
            return txt.format(**kwargs)
        except (KeyError, IndexError):
            return txt
    return txt


# ─── Detection de la langue ────────────────────────────────────
def detect_language_from_args() -> Optional[str]:
    """Cherche --lang=fr ou --lang=en dans sys.argv."""
    import sys
    for arg in sys.argv[1:]:
        if arg.startswith('--lang='):
            lang = arg.split('=', 1)[1].strip().lower()
            if lang in TRANSLATIONS:
                return lang
    return None


def load_language_from_config(config_path: str) -> Optional[str]:
    """Lit la langue depuis config.json si presente."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        lang = cfg.get('language')
        if lang in TRANSLATIONS:
            return lang
    except (OSError, json.JSONDecodeError):
        pass
    return None


def save_language_to_config(config_path: str, lang: str) -> None:
    """Sauvegarde la langue dans config.json."""
    try:
        cfg = {}
        cp = Path(config_path)
        if cp.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        cfg['language'] = lang
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
