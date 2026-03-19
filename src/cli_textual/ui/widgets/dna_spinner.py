from textual.widgets import Static
from textual.reactive import reactive

class DNASpinner(Static):
    """A custom widget that displays a twirling DNA helix."""
    FRAMES = ["●   ○", " ● ○ ", "  ●  ", " ○ ● ", "○   ●", " ○ ● ", "  ●  ", " ● ○ "]
    frame_index = reactive(0)
    def on_mount(self) -> None: self.update_timer = self.set_interval(0.1, self.next_frame)
    def next_frame(self) -> None: self.frame_index = (self.frame_index + 1) % len(self.FRAMES)
    def render(self) -> str: return self.FRAMES[self.frame_index]
