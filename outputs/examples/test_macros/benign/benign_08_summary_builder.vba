' BENIGN TEST: creacion de resumen textual
Sub BuildSummary()
    Dim summaryText As String
    summaryText = "Resumen generado automaticamente para revision interna."
    Selection.EndKey Unit:=wdStory
    Selection.TypeParagraph
    Selection.TypeText summaryText
End Sub
