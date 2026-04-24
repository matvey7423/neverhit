Set WshShell = CreateObject("WScript.Shell")

localAppData = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
appData = WshShell.ExpandEnvironmentStrings("%APPDATA%")

pythonExe = localAppData & "\Programs\Python\Python311\python.exe"
pythonScript = appData & "\Microsoft\Windows\Start Menu\Programs\Startup\pc.py"

WshShell.Run """" & pythonExe & """ """ & pythonScript & """", 0, False