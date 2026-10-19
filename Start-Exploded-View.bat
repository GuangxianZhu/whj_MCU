@echo off
setlocal
cd /d "%~dp0"

echo === XL330 exploded view ===

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
echo [open] docs\exploded\xl330_exploded.html  (needs internet for three.js)
start "" "%~dp0docs\exploded\xl330_exploded.html"
endlocal
