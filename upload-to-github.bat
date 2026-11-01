@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title MicroMouse Lab - Upload to GitHub

echo ============================================================
echo   MicroMouse Lab - GitHub uploader
echo   Source: %CD%
echo ============================================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Git is missing. Install Git for Windows from https://git-scm.com/download/win
  goto :failed
)
where gh >nul 2>&1
if errorlevel 1 (
  echo [ERROR] GitHub CLI is missing.
  echo Install it using: winget install --id GitHub.cli -e
  echo Then reopen this batch file so the updated PATH is available.
  goto :failed
)

echo [1/5] Checking GitHub authentication...
gh auth status --hostname github.com >nul 2>&1
if errorlevel 1 (
  echo You are not logged in to GitHub CLI, or your login has expired.
  echo A browser sign-in will open. Do not enter passwords into this batch file.
  gh auth login --hostname github.com --git-protocol https --web
  if errorlevel 1 goto :failed
)
gh auth status --hostname github.com
if errorlevel 1 goto :failed
gh auth setup-git --hostname github.com
if errorlevel 1 goto :failed

echo.
echo [2/5] Checking Git commit identity...
set "GIT_NAME="
for /f "delims=" %%I in ('git config user.name 2^>nul') do set "GIT_NAME=%%I"
if not defined GIT_NAME (
  echo Git needs a name for commits. This is stored in this repository only.
  set /p "GIT_NAME=Git author name: "
  if not defined GIT_NAME goto :failed
)
set "GIT_EMAIL="
for /f "delims=" %%I in ('git config user.email 2^>nul') do set "GIT_EMAIL=%%I"
if not defined GIT_EMAIL (
  set /p "GIT_EMAIL=Git author email (GitHub noreply is fine): "
  if not defined GIT_EMAIL goto :failed
)

echo.
echo [3/5] Preparing local Git repository...
set "INSIDE="
for /f "delims=" %%I in ('git rev-parse --is-inside-work-tree 2^>nul') do set "INSIDE=%%I"
if not "%INSIDE%"=="true" (
  git init -b main
  if errorlevel 1 goto :failed
) else (
  set "PREFIX="
  for /f "delims=" %%I in ('git rev-parse --show-prefix 2^>nul') do set "PREFIX=%%I"
  if defined PREFIX (
    echo [ERROR] This folder belongs to a PARENT Git repository.
    echo Move the MicroMouse Lab folder outside that repository before uploading.
    goto :failed
  )
)
if defined GIT_NAME git config --local user.name "%GIT_NAME%"
if defined GIT_EMAIL git config --local user.email "%GIT_EMAIL%"
git config user.name >nul 2>&1
if errorlevel 1 goto :failed
git config user.email >nul 2>&1
if errorlevel 1 goto :failed

git add --all
if errorlevel 1 goto :failed
echo.
echo Files prepared for upload:
git status --short
echo.
choice /c YN /n /m "Commit these changes and prepare a GitHub push? [Y/N]: "
if errorlevel 2 goto :cancelled

git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Update MicroMouse Lab"
  if errorlevel 1 goto :failed
) else (
  echo No new changes to commit; existing commits will be pushed.
)

set "ORIGIN="
for /f "delims=" %%I in ('git remote get-url origin 2^>nul') do set "ORIGIN=%%I"
if not defined ORIGIN (
  call :create_repo
  if errorlevel 1 goto :failed
) else (
  echo [4/5] Existing origin remote: %ORIGIN%
  echo The uploader will NOT change the remote repository URL.
)

echo.
echo [5/5] Pushing to origin...
git remote -v
choice /c YN /n /m "Push commits to this GitHub repository now? [Y/N]: "
if errorlevel 2 goto :cancelled
for /f "delims=" %%B in ('git branch --show-current') do set "BRANCH=%%B"
if not defined BRANCH (
  echo [ERROR] Cannot determine local branch.
  goto :failed
)
git push -u origin "%BRANCH%"
if errorlevel 1 goto :failed

echo.
echo [SUCCESS] MicroMouse Lab uploaded to GitHub.
gh repo view --web
pause
exit /b 0

:cancelled
echo Cancelled. Your local files and existing Git history are preserved.
pause
exit /b 1

:failed
echo.
echo [ERROR] Upload stopped. Read the messages above; no forced push was performed.
pause
exit /b 1

:create_repo
echo.
echo [4/5] Create a GitHub repository...
set "REPO_NAME=micromouse-lab"
set "REPO_INPUT="
set /p "REPO_INPUT=Repository name [micromouse-lab]: "
if defined REPO_INPUT set "REPO_NAME=%REPO_INPUT%"
echo Choose visibility. PRIVATE is recommended while experimenting.
choice /c PR /n /m "[P]rivate / [R] public: "
if errorlevel 2 goto :create_public
echo Creating a PRIVATE repository.
gh repo create "%REPO_NAME%" --private --source=. --remote=origin
if errorlevel 1 exit /b 1
exit /b 0

:create_public
echo Creating a PUBLIC repository.
gh repo create "%REPO_NAME%" --public --source=. --remote=origin
if errorlevel 1 exit /b 1
exit /b 0
