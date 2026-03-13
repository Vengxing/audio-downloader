Set objShell = WScript.CreateObject("WScript.Shell")
' Run the batch file silently (0 means hide window)
objShell.Run "cmd /c ""run.bat""", 0, False
