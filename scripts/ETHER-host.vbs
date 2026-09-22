Set s=CreateObject("WScript.Shell")
s.CurrentDirectory="C:\Users\Otcde\ETHER"
s.Run """C:\Users\Otcde\ETHER\.venv\Scripts\pythonw.exe"" ""C:\Users\Otcde\ETHER\scripts\ether_keepalive.py""", 0, False
