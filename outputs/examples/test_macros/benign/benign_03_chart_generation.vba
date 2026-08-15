' BENIGN TEST: generacion de grafico
Sub CreateSalesChart()
    Dim chartTitle As String
    chartTitle = "Resumen de ventas"
    ActiveSheet.Shapes.AddChart2.Select
    ActiveChart.ChartTitle.Text = chartTitle
End Sub
