' BENIGN TEST: ajuste de diapositivas
Sub NormalizeSlides()
    Dim slideItem As Slide
    For Each slideItem In ActivePresentation.Slides
        slideItem.FollowMasterBackground = msoTrue
    Next slideItem
End Sub
