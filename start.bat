@echo off
setlocal enabledelayedexpansion
title T470s UEFI Unlock Operator

REM ════════════════════════════════════════════════════════════════
REM  Bootstrap : utilise le Python deja installe sur le systeme.
REM  Si Python n'est pas installe (ou pas de tkinter), on telecharge
REM  l'installeur Python officiel et on le lance pour que
REM  l'utilisateur fasse l'installation manuelle (avec UI standard).
REM
REM  Ce script est bilingue FR/EN par necessite : il s'execute AVANT
REM  Python, donc le choix de langue Tkinter n'est pas encore
REM  possible. Toutes les chaines sont affichees dans les 2 langues.
REM ════════════════════════════════════════════════════════════════

cd /d "%~dp0"

set "ROOT=%cd%"
set "PYTHON_VERSION=3.11.9"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe"
set "PYTHON_RETRY_COUNT=0"

REM ─── Banniere ─────────────────────────────────────────────────
echo.
echo  ============================================================
echo                T470s UEFI Unlock Operator
echo  ============================================================
echo.

REM ─── Detection Python ─────────────────────────────────────────
:check_python
echo [1/3] Detection de Python  /  Detecting Python...

set "PYTHON_EXE="

REM Essayer 'python' dans le PATH avec tkinter
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys, tkinter; assert sys.version_info[0] >= 3" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
        for /f "tokens=*" %%V in ('python --version 2^>^&1') do echo       %%V  ^(avec tkinter / with tkinter^)
        goto :python_ok
    )
)

REM Essayer 'py' (Python Launcher Windows)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import tkinter" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=py -3"
        for /f "tokens=*" %%V in ('py -3 --version 2^>^&1') do echo       %%V  ^(avec tkinter / with tkinter^)
        goto :python_ok
    )
)

REM ─── Fallback : chercher Python aux emplacements typiques ─────
REM Apres une install fraiche, le PATH du process actuel n'est pas
REM forcement a jour. On cherche python.exe aux emplacements standard
REM d'installation Windows (per-user et system-wide).
for %%P in (
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "%LocalAppData%\Programs\Python\Python310\python.exe"
    "%LocalAppData%\Programs\Python\Python39\python.exe"
    "C:\Program Files\Python313\python.exe"
    "C:\Program Files\Python312\python.exe"
    "C:\Program Files\Python311\python.exe"
    "C:\Program Files\Python310\python.exe"
    "C:\Program Files\Python39\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
    "C:\Python39\python.exe"
) do (
    if exist "%%~P" (
        "%%~P" -c "import sys, tkinter; assert sys.version_info[0] >= 3" >nul 2>nul
        if not errorlevel 1 (
            set PYTHON_EXE="%%~P"
            for /f "tokens=*" %%V in ('"%%~P" --version 2^>^&1') do echo       %%V detecte / detected ^(avec tkinter / with tkinter^)
            echo       Chemin / Path: %%~P
            goto :python_ok
        )
    )
)

REM ─── Python absent ou sans tkinter : on telecharge l'installeur
echo       Python non detecte ^(ou sans tkinter^)  /  not detected ^(or without tkinter^).

REM Compteur de retry : on n'essaye que 3 fois max pour ne pas boucler infiniment
set /a PYTHON_RETRY_COUNT+=1
if !PYTHON_RETRY_COUNT! GTR 3 (
    echo.
    echo  [FR] [ERREUR] Python n'a pas pu etre installe apres 3 tentatives.
    echo       Installez Python manuellement depuis : https://www.python.org/downloads/
    echo       Important : cochez "Add python.exe to PATH" pendant l'install.
    echo       Puis relancez ce script.
    echo.
    echo  [EN] [ERROR] Python could not be installed after 3 attempts.
    echo       Install Python manually from: https://www.python.org/downloads/
    echo       Important: check "Add python.exe to PATH" during install.
    echo       Then re-run this script.
    pause
    exit /b 1
)
echo.
echo  ============================================================
echo    Installation de Python requise
echo    Python installation required
echo  ============================================================
echo.
echo  [FR] L'installeur officiel de Python %PYTHON_VERSION% va etre
echo       telecharge et lance. Vous aurez juste a :
echo.
echo         1. COCHER  [X] "Add python.exe to PATH"  ^(en bas^)
echo         2. CLIQUER  "Customize installation"
echo         3. VERIFIER que [X] "tcl/tk and IDLE" est coche
echo         4. CLIQUER  Next, puis Install
echo         5. ATTENDRE la fin ^(quelques minutes^)
echo         6. CLIQUER  Close
echo.
echo       Une fois ferme, la verification se relancera automatiquement.
echo.
echo  [EN] The official Python %PYTHON_VERSION% installer will be
echo       downloaded and launched. You will only need to:
echo.
echo         1. CHECK   [X] "Add python.exe to PATH"  ^(bottom^)
echo         2. CLICK   "Customize installation"
echo         3. VERIFY  [X] "tcl/tk and IDLE" is checked
echo         4. CLICK   Next, then Install
echo         5. WAIT    for completion ^(a few minutes^)
echo         6. CLICK   Close
echo.
echo       Once closed, verification will restart automatically.
echo.
echo  ------------------------------------------------------------
echo   Appuyez sur une touche pour continuer  /  Press any key to continue
echo  ------------------------------------------------------------
pause >nul

set "PY_INSTALLER=%TEMP%\python_installer_%PYTHON_VERSION%.exe"

REM Telechargement
echo.
echo  [FR] Telechargement de l'installeur Python %PYTHON_VERSION% ^(~28 Mo^)...
echo  [EN] Downloading Python %PYTHON_VERSION% installer ^(~28 MB^)...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PY_INSTALLER%' -UseBasicParsing -ErrorAction Stop; Write-Host '       OK' } catch { Write-Host ('[ERREUR / ERROR] ' + $_.Exception.Message); exit 1 }"

if errorlevel 1 (
    echo.
    echo  [FR] [ERREUR] Telechargement echoue.
    echo       Verifiez votre connexion Internet et reessayez.
    echo       Ou installez Python manuellement depuis : https://www.python.org/downloads/
    echo.
    echo  [EN] [ERROR] Download failed.
    echo       Check your Internet connection and retry.
    echo       Or install Python manually from: https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist "%PY_INSTALLER%" (
    echo.
    echo  [FR] [ERREUR] Fichier installeur introuvable apres telechargement.
    echo  [EN] [ERROR] Installer file not found after download.
    pause
    exit /b 1
)

REM Lancement de l'installeur Python (interface graphique standard)
echo.
echo  [FR] Lancement de l'installeur Python...
echo       ^(suivez les etapes affichees, puis fermez l'installeur^)
echo  [EN] Launching Python installer...
echo       ^(follow the steps shown, then close the installer^)
echo.

start "" /wait "%PY_INSTALLER%"

REM Nettoyage de l'installeur telecharge
del "%PY_INSTALLER%" >nul 2>nul

echo.
echo  [FR] Installation terminee. Re-verification...
echo  [EN] Installation done. Re-checking...
echo.

REM ─── Rechargement du PATH apres installation Python ───────────
REM ATTENTION : on doit preserver le PATH systeme essentiel (System32)
REM sinon on perd powershell.exe, reg.exe, where.exe, etc.
REM
REM Strategie :
REM   1. Memoriser un PATH minimal sur (System32) au cas ou
REM   2. Lire HKLM (PATH systeme) et HKCU (PATH utilisateur) depuis
REM      le registre
REM   3. Construire le nouveau PATH : SystemRoot d'abord, puis HKLM,
REM      puis HKCU
set "SAFE_PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SystemRoot%\System32\WindowsPowerShell\v1.0"

set "USER_PATH="
set "SYS_PATH="

for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v PATH 2^>nul ^| findstr /i "REG_"') do set "USER_PATH=%%B"
for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul ^| findstr /i "REG_"') do set "SYS_PATH=%%B"

REM Si la lecture du registre echoue, on garde au moins le SAFE_PATH
if defined SYS_PATH (
    set "PATH=%SYS_PATH%;%USER_PATH%;%SAFE_PATH%"
) else (
    set "PATH=%SAFE_PATH%;%USER_PATH%"
)

REM Petite attente pour laisser le PATH se propager
timeout /t 2 /nobreak >nul 2>nul

echo  ------------------------------------------------------------
echo   Appuyez sur une touche pour continuer  /  Press any key to continue
echo  ------------------------------------------------------------
pause >nul

REM Reverification (boucle sur :check_python)
goto :check_python

:python_ok
echo.

REM ─── Etape 2a : Selection de la langue (au premier lancement) ─
REM A partir d'ici Python est dispo, donc l'app peut prendre le relai
REM pour le reste en respectant la langue choisie.
if not exist "%ROOT%\config.json" (
    echo [2/3] Selection de la langue  /  Language selection...
    %PYTHON_EXE% "%ROOT%\app\language_selector.py" > "%ROOT%\.lang.tmp"
    set /p SELECTED_LANG=<"%ROOT%\.lang.tmp"
    del "%ROOT%\.lang.tmp" >nul 2>nul
    echo       Langue choisie / Selected: !SELECTED_LANG!
    REM Sauvegarder la langue dans un config.json minimal pour que
    REM l'installeur la trouve immediatement.
    echo {"language": "!SELECTED_LANG!"} > "%ROOT%\config.json"
) else (
    echo [2/3] Configuration existante detectee  /  Existing configuration detected.
)
echo.

REM ─── Etape 2b : Installeur de composants ──────────────────────
echo Verification des composants  /  Verifying components...
echo.

%PYTHON_EXE% "%ROOT%\installer\installer.py"
set "INSTALL_CODE=%errorlevel%"

if not "%INSTALL_CODE%"=="0" (
    echo.
    echo  [FR] [ERREUR] Installeur termine avec code %INSTALL_CODE%.
    echo  [EN] [ERROR] Installer ended with code %INSTALL_CODE%.
    pause
    exit /b 1
)

REM ─── Etape 3 : Application ────────────────────────────────────
echo.
echo [3/3] Lancement de l'application  /  Launching application...
echo.

%PYTHON_EXE% "%ROOT%\app\operator_gui.py"

if errorlevel 1 (
    echo.
    echo  [FR] L'application s'est fermee avec une erreur.
    echo  [EN] The application closed with an error.
    pause
)

endlocal
exit /b 0
