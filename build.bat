@echo off
echo Installing dependencies...
pip install customtkinter pyinstaller
echo.
echo Building GCodeEditor.exe...
pyinstaller --onefile --windowed --name "GCodeEditor" --collect-data customtkinter main.py
echo.
echo Done! Executable is at: dist\GCodeEditor.exe
pause
