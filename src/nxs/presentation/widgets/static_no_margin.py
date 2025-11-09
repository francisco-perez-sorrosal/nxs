from textual.widgets import Static


class StaticNoMargin(Static):
    """Static widget with zero padding/margin so it consumes only content height."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.styles.height = "auto"
        self.styles.margin = 0
        self.styles.padding = 0
        self.styles.width = "100%"
