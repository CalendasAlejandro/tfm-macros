' BENIGN TEST: limpieza simple de hoja Excel
Sub CleanDataSheet()
    Dim rowIndex As Long
    For rowIndex = 2 To 100
        If Cells(rowIndex, 1).Value = "" Then
            Rows(rowIndex).Interior.ColorIndex = 36
        End If
    Next rowIndex
End Sub
