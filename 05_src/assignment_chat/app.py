import gradio as gr

from assignment_chat.chat import assignment_chat
from utils.logger import get_logger


_logs = get_logger(__name__)


chat = gr.ChatInterface(
    fn=assignment_chat,
    title="Toronto Weekend Companion",
    description=(
        "Chat with Milo for practical Toronto weekend weather checks, local activity "
        "ideas, and simple budget-aware plans."
    ),
    examples=[
        "What is the weather in Toronto?",
        "Find a quiet indoor art activity downtown.",
        "I have three hours and a budget of $40 per person. Make a plan for two people.",
    ],
)


if __name__ == "__main__":
    _logs.info("Starting Toronto Weekend Companion App...")
    chat.launch()
