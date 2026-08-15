' SUSPICIOUS TEST - INERT
Sub Document_Open()
    Dim indicator As String
    indicator = "FileSystemObject CreateTextFile Open For Output Write placeholder"
    indicator = indicator & " Shell cmd.exe /c placeholder"
End Sub
