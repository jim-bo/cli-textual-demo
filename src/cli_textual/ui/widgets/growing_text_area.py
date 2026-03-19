from textual import events
from textual.widgets import TextArea, OptionList
from textual.message import Message

class GrowingTextArea(TextArea):
    """A TextArea that grows with content and handles submission on Enter."""
    class Submitted(Message):
        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    def _on_key(self, event: events.Key) -> None:
        try:
            autocomplete = self.app.query_one("#autocomplete-list", OptionList)
            is_autocomplete_visible = autocomplete.has_class("visible")
        except:
            is_autocomplete_visible = False

        if event.key == "enter":
            user_input = self.text.strip()
            if user_input:
                event.prevent_default(); event.stop()
                self.text = ""; self.styles.height = 1
                self.post_message(self.Submitted(user_input))
        
        elif event.key == "down" and is_autocomplete_visible:
            event.prevent_default(); event.stop()
            if autocomplete.option_count > 0:
                current = autocomplete.highlighted or 0
                autocomplete.highlighted = (current + 1) % autocomplete.option_count
        
        elif event.key == "up" and is_autocomplete_visible:
            event.prevent_default(); event.stop()
            if autocomplete.option_count > 0:
                current = autocomplete.highlighted or 0
                autocomplete.highlighted = (current - 1) % autocomplete.option_count
        
        elif event.key == "tab" and is_autocomplete_visible:
            if autocomplete.highlighted is not None:
                event.prevent_default(); event.stop()
                option = autocomplete.get_option_at_index(autocomplete.highlighted)
                command = str(option.prompt).split()[0]
                self.text = command + " "
                autocomplete.set_class(False, "visible")
                self.move_cursor((0, len(self.text)))
