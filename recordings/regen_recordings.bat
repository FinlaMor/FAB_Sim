@echo off
REM Regenerate the replay recordings with the current engine.
REM Records fresh games (not rebuilt from stale jsonl) so engine changes show up.
REM Run by double-clicking, or from a terminal: recordings\regen_recordings.bat
setlocal
REM %~dp0 is this file's folder (…\recordings\); ".." is the project root.
cd /d "%~dp0.."

echo Regenerating Victor vs Kayo...
python scripts\make_replay.py --deck1 decks\victor_goldmane_high_and_mighty_CC_lite.txt --deck2 decks\kayo_underhanded_cheat_CC_lite.txt --seed 11 -o recordings\replay_victor_vs_kayo.html
if errorlevel 1 goto :error

echo Regenerating Kayo vs Arakni...
python scripts\make_replay.py --deck1 decks\kayo_underhanded_cheat_CC_lite.txt --deck2 decks\arakni_marionette_CC_lite.txt --seed 11 -o recordings\replay_kayo_vs_arakni.html
if errorlevel 1 goto :error

echo.
echo Done. Recordings written to the recordings\ folder.
goto :done

:error
echo.
echo FAILED (see output above). Is Python on PATH and are you in the FAB_Sim repo?

:done
endlocal
pause
