' SUSPICIOUS TEST - INERT
Sub Document_Open()
    Dim hiddenText As String
    hiddenText = "Chr(80) & Chr(111) & Chr(119) & Chr(101) & Chr(114) & Chr(83) & Chr(104) & Chr(101) & Chr(108) & Chr(108)"
    hiddenText = hiddenText & " + CreateObject(""WScript.Shell"")"
End Sub
