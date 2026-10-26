@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo === ORCA hand through KM1M7C bridge ===

rem ---------- 1. update this repo (whj_MCU main) ----------
where git >nul 2>nul
if errorlevel 1 (
  echo [error] git not found. Install Git for Windows first.
  pause
  exit /b 1
)
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set BRANCH=%%b
echo [update] whj_MCU branch: %BRANCH%
git fetch origin main
if errorlevel 1 (
  echo [update] cannot reach GitHub, using local copy.
) else (
  if /i "%BRANCH%"=="main" (
    git pull --ff-only origin main
    if errorlevel 1 echo [update] pull failed ^(local changes?^), using local copy.
  ) else (
    echo [update] not on main, skip pull. Run "git checkout main" to get updates.
  )
)

rem ---------- 2. get / update orca_core ----------
set "ORCA=%~dp0tools\orca\orca_core"
if not exist "%ORCA%\.git" (
  echo [orca] cloning orcahand/orca_core ...
  git clone https://github.com/orcahand/orca_core "%ORCA%"
  if errorlevel 1 ( echo [error] clone failed. & pause & exit /b 1 )
) else (
  echo [orca] updating orca_core main ...
  git -C "%ORCA%" pull --ff-only origin main
  if errorlevel 1 echo [orca] pull failed, using local copy.
)

rem ---------- 3. Python environment (uv) ----------
where uv >nul 2>nul
if errorlevel 1 (
  echo [error] uv not found. Install it with this PowerShell command, then re-run:
  echo    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
  pause
  exit /b 1
)
echo [env] uv sync ...
uv sync --project "%ORCA%"
if errorlevel 1 ( echo [error] uv sync failed. & pause & exit /b 1 )

set "RUN=uv run --project "%ORCA%" python"
set "CFG=%~dp0tools\orca\my_hand\config.yaml"

rem ---------- 4. first run: make our config (COM port, side) ----------
if not exist "%CFG%" goto makecfg
goto menu

:makecfg
echo.
echo Serial ports on this PC:
%RUN% "%~dp0tools\orca\make_config.py" --list
set /p COMPORT=KM1M7C COM port (e.g. COM5):
set /p SIDE=Hand side, right or left [right]:
if "%SIDE%"=="" set SIDE=right
set /p BAUD=Bridge servo-side baud [57600]:
if "%BAUD%"=="" set BAUD=57600
%RUN% "%~dp0tools\orca\make_config.py" "%ORCA%" --side %SIDE% --port %COMPORT% --baud %BAUD%
if errorlevel 1 ( pause & goto menu )

:menu
echo.
echo ===== config: tools\orca\my_hand\config.yaml =====
echo  1  scan bus (list every motor that answers)          read only
echo  2  manual control, one slider per MOTOR (tendon work) moves
echo  3  configure motor chain (set IDs 1-17, one by one)  WRITES EEPROM
echo  4  check one motor (sweep)                           moves
echo  5  tension tendons                                   moves
echo  6  calibrate (drive every joint to its hardstops)    moves
echo  7  neutral pose                                      moves
echo  8  manual control, one slider per JOINT (after calib) moves
echo  9  change COM port / side / baud
echo  0  exit
set /p CHOICE=Choose:
if "%CHOICE%"=="1" %RUN% "%ORCA%\scripts\configure_motor_chain.py" "%CFG%" --scan & goto menu
if "%CHOICE%"=="2" %RUN% "%ORCA%\scripts\manual_control.py" "%CFG%" --motor-space & goto menu
if "%CHOICE%"=="3" %RUN% "%ORCA%\scripts\configure_motor_chain.py" "%CFG%" & goto menu
if "%CHOICE%"=="4" (
  set /p MID=Motor ID:
  %RUN% "%ORCA%\scripts\check_motor.py" "%CFG%" --motor-id !MID!
  goto menu
)
if "%CHOICE%"=="5" %RUN% "%ORCA%\scripts\tension.py" "%CFG%" & goto menu
if "%CHOICE%"=="6" %RUN% "%ORCA%\scripts\calibrate.py" "%CFG%" & goto menu
if "%CHOICE%"=="7" %RUN% "%ORCA%\scripts\neutral.py" "%CFG%" & goto menu
if "%CHOICE%"=="8" %RUN% "%ORCA%\scripts\manual_control.py" "%CFG%" & goto menu
if "%CHOICE%"=="9" goto makecfg
if "%CHOICE%"=="0" goto end
goto menu

:end
endlocal
