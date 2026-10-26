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

rem ---------- 2. get / update orca_core and orca_ui ----------
set "ORCA=%~dp0tools\orca\orca_core"
set "ORCAUI=%~dp0tools\orca\orca_ui"
call :getrepo orca_core "%ORCA%" || ( pause & exit /b 1 )
call :getrepo orca_ui "%ORCAUI%"

rem ---------- 3. Python environment (uv) ----------
where uv >nul 2>nul
if errorlevel 1 (
  echo [error] uv not found. Install it with this PowerShell command, then re-run:
  echo    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
  pause
  exit /b 1
)
echo [env] uv sync orca_core ...
uv sync --project "%ORCA%"
if errorlevel 1 ( echo [error] uv sync failed. & pause & exit /b 1 )

set "RUN=uv run --project "%ORCA%" python"
set "S=%ORCA%\scripts"
set "E=%ORCA%\examples"
set "HAND=%~dp0tools\orca\my_hand"
set "CFG=%HAND%\config.yaml"
set "REC=%HAND%\recordings"

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
if errorlevel 1 pause
goto menu

:menu
echo.
echo ===== config: tools\orca\my_hand\config.yaml =====
echo  --- SETUP ---
echo  1  scan bus (list every motor that answers)            read only
echo  2  configure motor chain (set IDs 1-17, one by one)    WRITES EEPROM
echo  3  check one finger motor (small sweep)                moves
echo  4  check wrist motor (small sweep)                     moves
echo  5  tension tendons (hold, then ratchet by hand)        moves
echo  6  calibrate all joints (drive to hardstops)           moves
echo  7  calibrate wrist only (re-do wrist)                  moves
echo  8  full setup wizard: 3x tension+calibrate + test      moves
echo  --- CONTROL ---
echo  11 neutral pose                                        moves
echo  12 zero pose                                           moves
echo  13 manual control, one slider per JOINT                moves
echo  14 manual control, one slider per MOTOR (tendon work)  moves
echo  15 demo: open - power grasp - pinch                    moves
echo  16 demo: fingers fan out / in                          moves
echo  17 stress test: open/close, watch temperatures         moves
echo  18 record poses (pose by hand, ENTER to save)          torque off
echo  19 replay recorded poses                               moves
echo  20 example program: finger + wrist (tools\orca\finger_wrist_example.py) moves
echo  --- OTHER ---
echo  W  web console orca_ui (setup + control + 3D in browser)
echo  C  change COM port / side / baud
echo  0  exit
set "CHOICE="
set /p CHOICE=Choose:
if "%CHOICE%"=="1"  %RUN% "%S%\configure_motor_chain.py" "%CFG%" --scan & goto menu
if "%CHOICE%"=="2"  %RUN% "%S%\configure_motor_chain.py" "%CFG%" & goto menu
if "%CHOICE%"=="3" (
  set /p MID=Motor ID:
  %RUN% "%S%\check_motor.py" "%CFG%" --motor-id !MID!
  goto menu
)
if "%CHOICE%"=="4"  %RUN% "%S%\check_motor.py" "%CFG%" --wrist & goto menu
if "%CHOICE%"=="5"  %RUN% "%S%\tension.py" "%CFG%" & goto menu
if "%CHOICE%"=="6"  %RUN% "%S%\calibrate.py" "%CFG%" & goto menu
if "%CHOICE%"=="7"  %RUN% "%S%\calibrate.py" "%CFG%" --joints wrist --force-wrist & goto menu
if "%CHOICE%"=="8"  %RUN% "%S%\setup.py" "%CFG%" & goto menu
if "%CHOICE%"=="11" %RUN% "%S%\neutral.py" "%CFG%" & goto menu
if "%CHOICE%"=="12" %RUN% "%S%\zero.py" "%CFG%" & goto menu
if "%CHOICE%"=="13" %RUN% "%S%\manual_control.py" "%CFG%" & goto menu
if "%CHOICE%"=="14" %RUN% "%S%\manual_control.py" "%CFG%" --motor-space & goto menu
if "%CHOICE%"=="15" %RUN% "%E%\main_demo.py" "%CFG%" --demo main & goto menu
if "%CHOICE%"=="16" %RUN% "%E%\main_demo.py" "%CFG%" --demo abduction & goto menu
if "%CHOICE%"=="17" %RUN% "%S%\stress_test.py" "%CFG%" & goto menu
if "%CHOICE%"=="18" (
  if not exist "%REC%" mkdir "%REC%"
  %RUN% "%E%\record_angles.py" "%CFG%" --output-dir "%REC%"
  goto menu
)
if "%CHOICE%"=="19" (
  echo Recordings:
  dir /b "%REC%\*.yaml" 2>nul
  set /p RFILE=File name:
  %RUN% "%E%\replay_angles.py" "%CFG%" --replay-file "%REC%\!RFILE!"
  goto menu
)
if "%CHOICE%"=="20" %RUN% "%~dp0tools\orca\finger_wrist_example.py" "%CFG%" & goto menu
if /i "%CHOICE%"=="W" goto webui
if /i "%CHOICE%"=="C" goto makecfg
if "%CHOICE%"=="0" goto end
goto menu

:webui
if not exist "%ORCAUI%\pyproject.toml" ( echo [error] orca_ui not downloaded. & goto menu )
echo [env] uv sync orca_ui ...
uv sync --project "%ORCAUI%"
if errorlevel 1 ( echo [error] uv sync failed. & goto menu )
echo [ui] http://localhost:5001  - press Ctrl+C here to stop it.
uv run --project "%ORCAUI%" orca-ui --config "%CFG%"
goto menu

rem ---------- helper: clone or update one orcahand repo ----------
:getrepo
if not exist "%~2\.git" (
  echo [orca] cloning orcahand/%~1 ...
  git clone https://github.com/orcahand/%~1 "%~2"
  if errorlevel 1 ( echo [error] clone of %~1 failed. & exit /b 1 )
) else (
  echo [orca] updating %~1 main ...
  git -C "%~2" pull --ff-only origin main
  if errorlevel 1 echo [orca] pull of %~1 failed, using local copy.
)
exit /b 0

:end
endlocal
