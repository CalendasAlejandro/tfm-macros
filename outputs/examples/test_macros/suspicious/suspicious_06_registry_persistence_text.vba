' SUSPICIOUS TEST - INERT
Sub AutoOpen()
    Dim indicator As String
    indicator = "WScript.Shell RegWrite HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run placeholder"
End Sub
