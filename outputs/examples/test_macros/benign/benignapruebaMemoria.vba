' ============================================
' Macro de automatización de documentos - Área Legal
' Genera un índice, aplica formato corporativo y guarda backup
' ============================================

Sub AutoOpen()
    Application.ScreenUpdating = False
    Call InicializarDocumento
    Application.ScreenUpdating = True
End Sub

Sub InicializarDocumento()
    Dim doc As Document
    Set doc = ActiveDocument
    
    ' Verifica si el documento ya fue procesado
    If DocumentoYaProcesado(doc) Then Exit Sub
    
    Call AplicarEstiloCorporativo(doc)
    Call GenerarIndice(doc)
    Call InsertarPieDePagina(doc)
    Call GuardarBackupLocal(doc)
    
    MsgBox "Documento formateado correctamente según plantilla corporativa.", vbInformation, "Automatización Legal"
End Sub

Function DocumentoYaProcesado(doc As Document) As Boolean
    On Error Resume Next
    DocumentoYaProcesado = (doc.CustomDocumentProperties("Procesado").Value = True)
    On Error GoTo 0
End Function

Sub AplicarEstiloCorporativo(doc As Document)
    Dim para As Paragraph
    For Each para In doc.Paragraphs
        If para.Range.Style = "Heading 1" Then
            para.Range.Font.Name = "Calibri"
            para.Range.Font.Size = 16
            para.Range.Font.Bold = True
            para.Range.Font.Color = RGB(0, 51, 102)
        ElseIf para.Range.Style = "Normal" Then
            para.Range.Font.Name = "Calibri"
            para.Range.Font.Size = 11
        End If
    Next para
End Sub

Sub GenerarIndice(doc As Document)
    Dim rng As Range
    Dim tocExists As Boolean
    tocExists = (doc.TablesOfContents.Count > 0)
    
    If Not tocExists Then
        Set rng = doc.Range(0, 0)
        rng.InsertParagraphAfter
        doc.TablesOfContents.Add Range:=rng, UseHeadingStyles:=True, _
            UpperHeadingLevel:=1, LowerHeadingLevel:=3
    End If
End Sub

Sub InsertarPieDePagina(doc As Document)
    Dim footer As HeaderFooter
    Set footer = doc.Sections(1).Footers(wdHeaderFooterPrimary)
    footer.Range.Text = "Confidencial - " & doc.Name & " - " & Format(Date, "dd/mm/yyyy")
    footer.Range.ParagraphFormat.Alignment = wdAlignParagraphCenter
End Sub

Sub GuardarBackupLocal(doc As Document)
    Dim rutaBackup As String
    Dim nombreArchivo As String
    
    ' Guarda backup en la carpeta Documentos del usuario, con timestamp
    rutaBackup = Environ("USERPROFILE") & "\Documents\Backups_Legal\"
    
    ' Crea la carpeta si no existe
    If Dir(rutaBackup, vbDirectory) = "" Then
        MkDir rutaBackup
    End If
    
    nombreArchivo = rutaBackup & Left(doc.Name, InStrRev(doc.Name, ".") - 1) & _
                    "_" & Format(Now, "yyyymmdd_hhmmss") & ".docx"
    
    doc.SaveAs2 FileName:=nombreArchivo, FileFormat:=wdFormatXMLDocument
    doc.Activate ' Vuelve al documento original
    
    ' Marca el documento como procesado
    On Error Resume Next
    doc.CustomDocumentProperties.Add Name:="Procesado", LinkToContent:=False, _
        Type:=msoPropertyTypeBoolean, Value:=True
    On Error GoTo 0
End Sub

Sub AutoClose()
    ' Limpieza al cerrar: pregunta si quiere conservar el backup
    Dim respuesta As VbMsgBoxResult
    respuesta = MsgBox("¿Desea conservar el backup generado en esta sesión?", vbYesNo + vbQuestion)
    If respuesta = vbNo Then
        Call LimpiarBackupsAntiguos
    End If
End Sub

Sub LimpiarBackupsAntiguos()
    Dim rutaBackup As String
    Dim archivo As String
    rutaBackup = Environ("USERPROFILE") & "\Documents\Backups_Legal\"
    
    archivo = Dir(rutaBackup & "*.docx")
    Do While archivo <> ""
        If DateDiff("d", FileDateTime(rutaBackup & archivo), Now) > 30 Then
            Kill rutaBackup & archivo
        End If
        archivo = Dir()
    Loop
End Sub