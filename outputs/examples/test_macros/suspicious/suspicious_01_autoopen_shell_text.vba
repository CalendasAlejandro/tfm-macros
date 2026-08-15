' SUSPICIOUS TEST - INERT
' The suspicious API names are stored as text for detector testing only.
Sub AutoOpen()
    Dim indicator As String
    indicator = "CreateObject(""WScript.Shell"").Run ""powershell -encodedcommand PLACEHOLDER"""
End Sub
