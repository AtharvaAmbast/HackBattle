Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd.exe /c cd C:\Users\AstrAkt\Git\HackBattle\cli && uvicorn api:app", 0, False