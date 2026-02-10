"""
Main NiceGUI page — Pro-grade ChatGPT/Perplexity-like interface.
Features: Streaming indicators, markdown rendering, smooth animations, loading states.
"""
import asyncio
import markdown
from typing import Optional
from datetime import datetime

from nicegui import ui, app

from deepmind.config import get_config
from deepmind.ui.theme import get_theme, generate_css, DARK_THEME, LIGHT_THEME
from deepmind.services.conversation_service import get_conversation_service
from deepmind.services.context_manager import get_context_manager
from deepmind.connectors.registry import get_connector_registry


class WorkspaceUI:
    """Main workspace UI controller with pro-grade features."""
    
    def __init__(self):
        self.cfg = get_config()
        self.theme_mode = self.cfg.ui.theme
        self.active_conversation_id: Optional[str] = None
        self.conversations = []
        self.messages = []
        self.context_stats = {}
        self.is_streaming = False
        self.current_stream_message = None
        
        # UI element references
        self.message_container = None
        self.input_area = None
        self.sidebar_list = None
        self.context_bar = None
        self.context_label = None
        self.theme_toggle = None
        self.send_button = None
        self.stop_button = None
        self.typing_indicator = None
        
        # Markdown renderer
        self.md = markdown.Markdown(extensions=['fenced_code', 'codehilite', 'tables', 'nl2br'])
    
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
            ui.input(placeholder="Search documents...").classes("w-full").props(
                "dense outlined"
            ).style(f"border-radius: 8px;")
            
            with ui.select(
                options=["GitHub", "Dropbox", "Google Drive"],
                value="GitHub",
                label="Source",
            ).classes("w-full").props("dense outlined"):
                pass
            
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
                    
                    # Send/Stop button (dynamic)
                    self.send_button = ui.button(
                        icon="send",
                        on_click=self._send_message,
                    ).props("round flat dense").style(
                        f"background: {theme['accent']}; color: white; "
                        f"width: 42px; height: 42px;"
                    )
                    
                    # Stop button (hidden by default)
                    self.stop_button = ui.button(
                        icon="stop",
                        on_click=self._stop_generation,
                    ).props("round flat dense").style(
                        f"background: {theme['error']}; color: white; "
                        f"width: 42px; height: 42px; display: none;"
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
            self.active_conversation_id = result["id"]
            self.conversations = await svc.list_conversations()
        else:
            self.active_conversation_id = self.conversations[0]["id"]
        
        await self._refresh_sidebar()
        await self._refresh_messages()
        await self._refresh_context()
    
    async def _refresh_sidebar(self):
        """Refresh the conversation list in sidebar."""
        if not self.sidebar_list:
            return
        
        self.sidebar_list.clear()
        theme = get_theme(self.theme_mode)
        
        with self.sidebar_list:
            for conv in self.conversations:
                is_active = conv["id"] == self.active_conversation_id
                card_class = "conversation-card active" if is_active else "conversation-card"
                
                with ui.card().classes(card_class).on("click", lambda c=conv: self._switch_conversation(c["id"])):
                    with ui.row().classes("w-full items-start gap-2"):
                        ui.icon("chat_bubble", size="sm").style(
                            f"color: {theme['accent'] if is_active else theme['text_tertiary']}"
                        )
                        with ui.column().classes("flex-grow gap-0"):
                            ui.label(conv["title"][:40]).classes("font-medium").style(
                                f"color: {theme['text_primary']}; font-size: 14px;"
                            )
                            if conv.get("updated_at"):
                                ui.label(self._format_time(conv["updated_at"])).classes("token-counter")
    
    async def _refresh_messages(self):
        """Refresh messages for active conversation."""
        if not self.active_conversation_id or not self.message_container:
            return
        
        svc = get_conversation_service()
        self.messages = await svc.get_messages(self.active_conversation_id)
        
        self.message_container.clear()
        theme = get_theme(self.theme_mode)
        
        with self.message_container:
            for msg in self.messages:
                self._render_message(msg, theme)
        
        await self._scroll_to_bottom()
    
    def _render_message(self, msg: dict, theme: dict):
        """Render a single message with markdown support."""
        is_user = msg["role"] == "user"
        bubble_class = "message-bubble message-user" if is_user else "message-bubble message-assistant"
        
        with ui.card().classes(bubble_class):
            with ui.row().classes("w-full items-start gap-3"):
                # Avatar icon
                if is_user:
                    ui.icon("person", size="sm").style(f"color: {theme['text_secondary']}")
                else:
                    ui.icon("smart_toy", size="sm").style(f"color: {theme['accent']}")
                
                with ui.column().classes("flex-grow gap-1"):
                    # Role label
                    ui.label("You" if is_user else "Assistant").classes("font-semibold").style(
                        f"color: {theme['text_primary']}; font-size: 14px;"
                    )
                    
                    # Message content (rendered as markdown for assistant)
                    if is_user:
                        ui.label(msg["content"]).style(f"color: {theme['text_primary']}; white-space: pre-wrap;")
                    else:
                        # Render markdown
                        html_content = self.md.convert(msg["content"])
                        ui.html(html_content).classes("markdown-content")
                    
                    # Timestamp
                    if msg.get("created_at"):
                        ui.label(self._format_time(msg["created_at"])).classes("token-counter mt-1")
    
    async def _send_message(self):
        """Send user message and stream AI response."""
        if self.is_streaming or not self.input_area.value.strip():
            return
        
        user_text = self.input_area.value.strip()
        self.input_area.value = ""
        self.is_streaming = True
        
        # Toggle buttons
        self.send_button.style("display: none;")
        self.stop_button.style("display: block;")
        
        theme = get_theme(self.theme_mode)
        
        try:
            # Show user message immediately
            with self.message_container:
                self._render_message({"role": "user", "content": user_text, "created_at": datetime.now().isoformat()}, theme)
            
            await self._scroll_to_bottom()
            
            # Show typing indicator
            with self.message_container:
                with ui.row().classes("items-center gap-2"):
                    ui.icon("smart_toy", size="sm").style(f"color: {theme['accent']}")
                    with ui.element("div").classes("typing-indicator") as self.typing_indicator:
                        ui.element("div").classes("typing-dot")
                        ui.element("div").classes("typing-dot")
                        ui.element("div").classes("typing-dot")
            
            await self._scroll_to_bottom()
            
            # Stream response
            svc = get_conversation_service()
            full_response = ""
            
            # Create assistant message card
            if self.typing_indicator:
                self.typing_indicator.parent_slot.parent.delete()
            
            with self.message_container:
                with ui.card().classes("message-bubble message-assistant") as msg_card:
                    with ui.row().classes("w-full items-start gap-3"):
                        ui.icon("smart_toy", size="sm").style(f"color: {theme['accent']}")
                        with ui.column().classes("flex-grow gap-1"):
                            ui.label("Assistant").classes("font-semibold").style(
                                f"color: {theme['text_primary']}; font-size: 14px;"
                            )
                            self.current_stream_message = ui.html("").classes("markdown-content")
            
            # Stream tokens
            async for chunk in svc.send_message_stream(self.active_conversation_id, user_text):
                if not self.is_streaming:  # Check for stop signal
                    break
                full_response += chunk
                self.current_stream_message.content = self.md.convert(full_response)
                await self._scroll_to_bottom()
            
            self.current_stream_message = None
            
            # Refresh to get persisted message
            await self._refresh_messages()
            await self._refresh_context()
            await self._refresh_sidebar()
            
        except Exception as e:
            ui.notify(f"Error: {str(e)}", type="negative")
        finally:
            self.is_streaming = False
            self.send_button.style("display: block;")
            self.stop_button.style("display: none;")
            if self.typing_indicator:
                try:
                    self.typing_indicator.parent_slot.parent.delete()
                except:
                    pass
    
    async def _stop_generation(self):
        """Stop ongoing generation."""
        self.is_streaming = False
        ui.notify("Stopping generation...", type="info")
    
    async def _on_enter(self, e):
        """Handle Enter key in input."""
        if not e.args.get("shiftKey"):
            await self._send_message()
    
    async def _new_conversation(self):
        """Create new conversation."""
        svc = get_conversation_service()
        result = await svc.create_conversation("New Chat")
        self.active_conversation_id = result["id"]
        self.conversations = await svc.list_conversations()
        await self._refresh_sidebar()
        await self._refresh_messages()
        await self._refresh_context()
        ui.notify("New conversation created", type="positive")
    
    async def _switch_conversation(self, conv_id: str):
        """Switch to different conversation."""
        self.active_conversation_id = conv_id
        await self._refresh_messages()
        await self._refresh_context()
        await self._refresh_sidebar()
    
    async def _refresh_context(self):
        """Update context usage indicator."""
        if not self.active_conversation_id:
            return
        
        ctx = get_context_manager()
        stats = ctx.get_stats(self.active_conversation_id)
        
        usage_pct = (stats["current_tokens"] / stats["max_tokens"]) * 100
        self.context_label.text = f"{usage_pct:.0f}%"
        self.context_bar.style(f"width: {usage_pct}%;")
        
        # Update color based on usage
        if usage_pct < 70:
            self.context_bar.classes(remove="context-moderate context-critical", add="context-healthy")
        elif usage_pct < 85:
            self.context_bar.classes(remove="context-healthy context-critical", add="context-moderate")
        else:
            self.context_bar.classes(remove="context-healthy context-moderate", add="context-critical")
        
        self.token_footer.text = f"{stats['current_tokens']:,} / {stats['max_tokens']:,} tokens"
    
    async def _refresh_connectors(self):
        """Refresh connector status list."""
        if not self.connector_list:
            return
        
        self.connector_list.clear()
        registry = get_connector_registry()
        theme = get_theme(self.theme_mode)
        
        with self.connector_list:
            for name, connector in registry.get_all().items():
                status = "connected" if connector.is_connected() else "disconnected"
                status_color = theme['success'] if status == "connected" else theme['text_tertiary']
                
                with ui.card().classes("w-full p-3").style(f"border-radius: 10px; border: 1px solid {theme['border']};"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("hub", size="sm").style(f"color: {status_color}")
                            ui.label(name.title()).style(f"color: {theme['text_primary']}; font-weight: 500;")
                        ui.label(status).classes("token-counter").style(f"color: {status_color};")
    
    async def _browse_documents(self):
        """Browse documents from connectors."""
        ui.notify("Document browser coming soon", type="info")
    
    async def _scroll_to_bottom(self):
        """Scroll message area to bottom."""
        await asyncio.sleep(0.05)
        if self.scroll_area:
            self.scroll_area.scroll_to(percent=1.0)
    
    def _toggle_theme(self, e):
        """Toggle between dark and light theme."""
        self.theme_mode = "dark" if e.value else "light"
        ui.notify(f"Switched to {self.theme_mode} mode. Refresh page to apply.", type="info")
    
    def _format_time(self, timestamp: str) -> str:
        """Format timestamp for display."""
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            now = datetime.now(dt.tzinfo)
            diff = now - dt
            
            if diff.days > 0:
                return f"{diff.days}d ago"
            elif diff.seconds >= 3600:
                return f"{diff.seconds // 3600}h ago"
            elif diff.seconds >= 60:
                return f"{diff.seconds // 60}m ago"
            else:
                return "just now"
        except:
            return timestamp[:10]
