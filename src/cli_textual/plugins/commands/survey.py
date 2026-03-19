from typing import List
from textual.widgets import Label, TabbedContent, TabPane, OptionList
from cli_textual.core.command import SlashCommand

class SurveyCommand(SlashCommand):
    name = "/survey"
    description = "Start a tabbed survey"
    requires_permission = True

    async def execute(self, app, args: List[str]):
        app.survey_answers = {}
        container = app.query_one("#interaction-container")
        container.add_class("visible")
        container.query("*").remove()
        
        container.mount(Label("Survey (Esc: cancel, Tab/Ctrl+N: next, Ctrl+P: prev)"))
        tabs = TabbedContent(id="survey-tabs")
        container.mount(tabs)
        
        async def populate():
            await tabs.add_pane(TabPane("Q1", OptionList("Python", "JS", id="opt-q1"), id="q1"))
            await tabs.add_pane(TabPane("Q2", OptionList("Textual", "Rich", id="opt-q2"), id="q2"))
            tabs.active = "q1"
            app.query_one("#opt-q1", OptionList).focus()
            
        app.set_timer(0.1, populate)
