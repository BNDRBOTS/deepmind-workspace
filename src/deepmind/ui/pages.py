"""
Main NiceGUI page — ChatGPT-like interface with sidebar, message area, input.
"""
import asyncio
from typing import Optional

from nicegui import ui, app

from deepmind.config import get_config
from deepmind.ui.theme import get_theme, generate_css, DARK_THEME, LIGHT_THEME
from deepmind.services.conversation_service import get_conversation_service
from deepmind.services.context_manager import get_context_manager
from deepmind.connectors.registry import get_connector_registry


class WorkspaceUI:
    """Main workspace UI controller."""
    
    def __init__(self):
        self.cfg = get_config()
        self.theme_mode = self.cfg.ui.theme
        self.current_conversation_id: Optional[str] = None
        self.conversations = []
        self.messages = []
        self.context_stats = {}
        self.is_streaming = False
        
        # UI element references
        self.message_container = None
        self.input_area = None
        self.sidebar_list = None
        self.context_bar = None
        self.context_label = None
        self.theme_toggle = None
    
    def build(self):
        """Build the complete UI layout."""
        theme = get_theme(self.theme_mode)
        
        ui.add_head_html(f"<style>{generate_css(theme)}</style>")
        ui.add_head_html("""
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
        """)
        
        with ui.header().classes("items-center justify-between px-4 py-2").style(
            f"background: {theme['bg_secondary']}; border-bottom: 1px solid {theme['border']}; height: 56px;"
        ):
            with ui.row().classes("items-center gap-3"):
                ui.icon("smart_toy", size="sm").style(f"color: {theme['accent']}")
                ui.label("DeepMind Workspace").classes("text-lg font-semibold").style(
                    f"color: {theme['text_primary']}; letter-spacing: -0.02em;"
                )
            
            with ui.row().classes("items-center gap-2"):
                # Context indicator in header
                with ui.row().classes("items-center gap-2"):
                    self.context_label = ui.label("0%").classes("token-counter")
                    with ui.element("div").classes("context-bar").style("width: 120px;"):
                        self.context_bar = ui.element("div").classes(
                            "context-bar-fill context-healthy"
                        ).style("width: 0%;")
                
                # Theme toggle
                self.theme_toggle = ui.switch(
                    "", value=(self.theme_mode == "dark"),
                    on_change=self._toggle_theme
                ).props("dense color=indigo").tooltip("Toggle dark/light mode")
                
                ui.icon("dark_mode" if self.theme_mode == "dark" else "light_mode",
                        size="xs").style(f"color: {theme['text_secondary']}")
        
        # Left Sidebar
        with ui.left_drawer(value=True).classes("p-0").style(
            f"width: {self.cfg.ui.sidebar_width}px; background: {theme['bg_secondary']}; "
            f"border-right: 1px solid {theme['border']};"
        ) as drawer:
            self._build_sidebar(theme)
        
        # Main Chat Area
        with ui.column().classes("w-full h-full").style(
            f"background: {theme['bg_primary']}; min-height: calc(100vh - 56px);"
        ):
            self._build_chat_area(theme)
        
        # Initialize
        ui.timer(0.1, self._init_data, once=True)
    
    def _build_sidebar(self, theme: dict):
        """Build the sidebar with conversations, documents, connectors."""
        with ui.column().classes("w-full h-full").style("padding: 0;"):
            # New Chat button
            with ui.row().classes("w-full p-3"):
                ui.button(
                    "New Chat", icon="add",
                    on_click=self._new_conversation
                ).classes("w-full").props(
                    "flat dense no-caps"
                ).style(
                    f"background: {theme['accent_soft']}; color: {theme['accent']}; "
                    f"border-radius: 10px; padding: 10px;"
                )
            
            # Tab navigation
            with ui.tabs().classes("w-full").props("dense no-caps") as tabs:
                chat_tab = ui.tab("Chats", icon="chat")
                docs_tab = ui.tab("Docs", icon="description")
                connect_tab = ui.tab("Connect", icon="hub")
            
            with ui.tab_panels(tabs, value=chat_tab).classes("w-full flex-grow"):
                # Chats panel
                with ui.tab_panel(chat_tab).classes("p-2"):
                    self.sidebar_list = ui.column().classes("w-full gap-1")
                
                # Documents panel
                with ui.tab_panel(docs_tab).classes("p-2"):
                    self._build_doc_browser(theme)
                
                # Connectors panel
                with ui.tab_panel(connect_tab).classes("p-2"):
                    self._build_connector_panel(theme)
    
    def _build_doc_browser(self, theme: dict):
        """Document browser in sidebar."""
        with ui.column().classes("w-full gap-2"):
            # Search
            ui.input(placeholder="Search documents...").classes("w-full").props(
                "dense outlined"
            ).style(f"border-radius: 8px;")
            
            # Connector selector
            with ui.select(
                options=["GitHub", "Dropbox", "Google Drive"],
                value="GitHub",
                label="Source",
            ).classes("w-full").props("dense outlined"):
                pass
            
            # Document tree / list
            self.doc_tree = ui.column().classes("w-full gap-1 mt-2")
            
            ui.button(
                "Browse", icon="folder_open",
                on_click=self._browse_documents,
            ).classes("w-full").props("flat dense no-caps").style(
                f"border-radius: 8px; color: {theme['text_secondary']};"
            )
    
    def _build_connector_panel(self, theme: dict):
        """Connector status and management panel."""
        self.connector_list = ui.column().classes("w-full gap-2")
        ui.timer(1, self._refresh_connectors, once=True)
    
    def _build_chat_area(self, theme: dict):
        """Main chat area with messages and input."""
        with ui.column().classes("w-full flex-grow").style(
            "max-width: 860px; margin: 0 auto; padding: 0 16px;"
        ):
            # Message display area
            with ui.scroll_area().classes("flex-grow w-full").style(
                "padding: 16px 0;"
            ) as scroll:
                self.message_container = ui.column().classes("w-full gap-4")
                self.scroll_area = scroll
            
            # Input area (fixed at bottom)
            with ui.column().classes("w-full").style(
                f"padding: 12px 0 20px 0; border-top: 1px solid {theme['border']};"
            ):
                # Pinned docs row
                self.pins_row = ui.row().classes("w-full gap-2 mb-2").style("min-height: 0;")
                
                # Input + send
                with ui.row().classes("w-full items-end gap-2"):
                    self.input_area = ui.textarea(
                        placeholder="Message DeepMind Workspace...",
                    ).classes("flex-grow chat-input").props(
                        "autogrow outlined dense rows=1 maxRows=6"
                    ).on("keydown.enter.prevent", self._on_enter)
                    
                    self.send_button = ui.button(
                        icon="send",
                        on_click=self._send_message,
                    ).props("round flat dense").style(
                        f"background: {theme['accent']}; color: white; "
                        f"width: 42px; height: 42px;"
                    )
                
                # Token usage footer
                with ui.row().classes("w-full justify-between mt-1"):
                    self.token_footer = ui.label("").classes("token-counter")
                    ui.label("DeepMind Workspace v1.0 · DeepSeek").classes("token-counter")
    
    # ---- Data Operations ----
    
    async def _init_data(self):
        """Initialize data on page load."""
        svc = get_conversation_service()
        self.conversations = await svc.list_conversations()
        
        if not self.conversations:
            result = await svc.create_conversation("Welcome")
            self.current_conversation_id = result["id"]
            self.conversations = await svc.list_conversations()
        else:
            self.current_conversation_id = self.conversations[0]["id"]
        
        await self._refresh_sidebar()
        await self._refresh_messages()
        await self._refresh_context()
    
    async def _refresh_sidebar(self):
        """Refresh the conversation list in sidebar."""
        if not self.sidebar_list:
            return
        
        self.sidebar_list.clear()
        theme = get_theme(self.theme_mode)
        
        with self