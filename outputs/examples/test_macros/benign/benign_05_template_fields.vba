' BENIGN TEST: actualizacion de campos de plantilla
Sub UpdateTemplateFields()
    Dim currentField As Field
    For Each currentField In ActiveDocument.Fields
        currentField.Update
    Next currentField
End Sub
