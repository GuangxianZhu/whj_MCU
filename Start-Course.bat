@echo off
setlocal
cd /d "%~dp0"

echo === ORCA hand embedded pitfall course ===

where git >nul 2>nul
if errorlevel 1 (
  echo [update] git not found, skip update check.
  goto open
)

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set BRANCH=%%b
echo [update] current branch: %BRANCH%
git fetch origin main
if errorlevel 1 (
  echo [update] cannot reach GitHub, using local copy.
  goto open
)
if /i "%BRANCH%"=="main" (
  git pull --ff-only origin main
  if errorlevel 1 echo [update] pull failed ^(local changes?^), using local copy.
) else (
  echo [update] not on main, skip pull. Run "git checkout main" to get updates.
)

:open
echo [open] docs\course\orca_pitfall_course.html  (works offline; progress is saved in this browser)
start "" "%~dp0docs\course\orca_pitfall_course.html"
endlocal
