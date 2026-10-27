@echo off
rem Windows: run Cantrip from this folder, e.g. cantrip ui. Needs Python 3.11 or newer (the py launcher).
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
py -3 -m cantrip %*
