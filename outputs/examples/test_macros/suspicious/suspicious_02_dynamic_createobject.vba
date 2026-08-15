' SUSPICIOUS TEST - INERT
' Dynamic CreateObject pattern represented as text, not executed.
Sub AutoOpen()
    Dim fragmentA As String
    Dim fragmentB As String
    fragmentA = "WScript"
    fragmentB = ".Shell"
    Dim indicator As String
    indicator = "CreateObject(fragmentA + fragmentB).ShowWindow = 0"
End Sub
