Attribute VB_Name = "ModuloInforme"

Sub GenerarResumenVentas()
    Dim ws As Worksheet
    Dim ultimaFila As Long
    Dim totalVentas As Double
    Dim i As Long

    Set ws = ThisWorkbook.Worksheets("Ventas")
    ultimaFila = ws.Cells(ws.Rows.Count, "A").End(xlUp).Row

    totalVentas = 0

    For i = 2 To ultimaFila
        If IsNumeric(ws.Cells(i, "C").Value) Then
            totalVentas = totalVentas + CDbl(ws.Cells(i, "C").Value)
        End If
    Next i

    ws.Range("E1").Value = "Resumen"
    ws.Range("E2").Value = "Total ventas"
    ws.Range("F2").Value = totalVentas
    ws.Range("E1:F2").Font.Bold = True
    ws.Range("E1:F2").Interior.Color = RGB(220, 235, 247)
    ws.Columns("E:F").AutoFit

    MsgBox "Resumen generado correctamente.", vbInformation
End Sub