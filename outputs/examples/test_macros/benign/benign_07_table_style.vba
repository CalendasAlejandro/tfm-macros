' BENIGN TEST: estilo de tablas
Sub StyleTables()
    Dim tableItem As Table
    For Each tableItem In ActiveDocument.Tables
        tableItem.Rows(1).Range.Bold = True
        tableItem.Borders.Enable = True
    Next tableItem
End Sub
