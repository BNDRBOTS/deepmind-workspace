"""
Pro-grade theme system for DeepMind Workspace.
ChatGPT/Perplexity-inspired design with smooth animations and polish.
"""

DARK_THEME = {
    "bg_primary": "#0d0d0d",
    "bg_secondary": "#1a1a1a",
    "bg_tertiary": "#242424",
    "bg_hover": "#2a2a2a",
    "text_primary": "#ececec",
    "text_secondary": "#a0a0a0",
    "text_tertiary": "#707070",
    "accent": "#3b82f6",
    "accent_soft": "rgba(59, 130, 246, 0.1)",
    "border": "#2a2a2a",
    "success": "#10b981",
    "warning": "#f59e0b",
    "error": "#ef4444",
}

LIGHT_THEME = {
    "bg_primary": "#ffffff",
    "bg_secondary": "#f8f8f8",
    "bg_tertiary": "#efefef",
    "bg_hover": "#e5e5e5",
    "text_primary": "#1a1a1a",
    "text_secondary": "#6b6b6b",
    "text_tertiary": "#9b9b9b",
    "accent": "#3b82f6",
    "accent_soft": "rgba(59, 130, 246, 0.08)",
    "border": "#e5e5e5",
    "success": "#10b981",
    "warning": "#f59e0b",
    "error": "#ef4444",
}


def get_theme(mode: str = "dark") -> dict:
    """Get theme colors based on mode."""
    return DARK_THEME if mode == "dark" else LIGHT_THEME


def generate_css(theme: dict) -> str:
    """Generate CSS with smooth animations and pro-grade styling."""
    return f"""
/* Reset and Base Styles */
* {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}}

body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
    background: {theme['bg_primary']};
    color: {theme['text_primary']};
    font-size: 15px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}}

/* Scrollbar Styling */
::-webkit-scrollbar {{
    width: 6px;
    height: 6px;
}}

::-webkit-scrollbar-track {{
    background: transparent;
}}

::-webkit-scrollbar-thumb {{
    background: {theme['border']};
    border-radius: 10px;
}}

::-webkit-scrollbar-thumb:hover {{
    background: {theme['text_tertiary']};
}}

/* Message Bubbles */
.message-bubble {{
    padding: 16px 20px;
    border-radius: 12px;
    margin-bottom: 12px;
    animation: slideIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    transition: all 0.2s ease;
}}

.message-bubble:hover {{
    background: {theme['bg_hover']} !important;
}}

.message-user {{
    background: {theme['bg_tertiary']};
    border: 1px solid {theme['border']};
}}

.message-assistant {{
    background: transparent;
}}

.message-assistant:hover {{
    background: {theme['bg_secondary']} !important;
}}

/* Chat Input */
.chat-input {{
    background: {theme['bg_secondary']} !important;
    border: 1.5px solid {theme['border']} !important;
    border-radius: 12px !important;
    padding: 12px 16px !important;
    font-size: 15px !important;
    color: {theme['text_primary']} !important;
    transition: all 0.2s ease !important;
    resize: none !important;
}}

.chat-input:focus {{
    border-color: {theme['accent']} !important;
    box-shadow: 0 0 0 3px {theme['accent_soft']} !important;
    outline: none !important;
}}

/* Buttons */
button {{
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    font-weight: 500 !important;
}}

button:hover {{
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
}}

button:active {{
    transform: translateY(0);
}}

/* Conversation Cards */
.conversation-card {{
    background: transparent;
    border-radius: 10px;
    padding: 12px;
    margin-bottom: 4px;
    cursor: pointer;
    transition: all 0.2s ease;
    border: 1px solid transparent;
}}

.conversation-card:hover {{
    background: {theme['bg_hover']};
    border-color: {theme['border']};
}}

.conversation-card.active {{
    background: {theme['accent_soft']};
    border-color: {theme['accent']};
}}

/* Loading Indicators */
.loading-pulse {{
    animation: pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}}

@keyframes pulse {{
    0%, 100% {{
        opacity: 1;
    }}
    50% {{
        opacity: 0.5;
    }}
}}

.typing-indicator {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 12px;
    background: {theme['bg_tertiary']};
    border-radius: 16px;
}}

.typing-dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: {theme['text_secondary']};
    animation: typingDot 1.4s infinite;
}}

.typing-dot:nth-child(2) {{
    animation-delay: 0.2s;
}}

.typing-dot:nth-child(3) {{
    animation-delay: 0.4s;
}}

@keyframes typingDot {{
    0%, 60%, 100% {{
        opacity: 0.3;
        transform: translateY(0);
    }}
    30% {{
        opacity: 1;
        transform: translateY(-8px);
    }}
}}

/* Animations */
@keyframes slideIn {{
    from {{
        opacity: 0;
        transform: translateY(10px);
    }}
    to {{
        opacity: 1;
        transform: translateY(0);
    }}
}}

@keyframes fadeIn {{
    from {{
        opacity: 0;
    }}
    to {{
        opacity: 1;
    }}
}}

/* Code Blocks */
pre {{
    background: {theme['bg_tertiary']} !important;
    border: 1px solid {theme['border']} !important;
    border-radius: 8px !important;
    padding: 16px !important;
    overflow-x: auto !important;
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
    font-size: 14px !important;
    line-height: 1.5 !important;
}}

code {{
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
    font-size: 14px !important;
    background: {theme['bg_tertiary']} !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
}}

/* Context Indicator */
.context-bar {{
    height: 6px;
    background: {theme['bg_tertiary']};
    border-radius: 10px;
    overflow: hidden;
}}

.context-bar-fill {{
    height: 100%;
    border-radius: 10px;
    transition: width 0.3s ease, background-color 0.3s ease;
}}

.context-healthy {{
    background: {theme['success']};
}}

.context-moderate {{
    background: {theme['warning']};
}}

.context-critical {{
    background: {theme['error']};
}}

/* Token Counter */
.token-counter {{
    font-size: 12px;
    color: {theme['text_tertiary']};
    font-weight: 500;
    font-variant-numeric: tabular-nums;
}}

/* Markdown Styling */
.markdown-content h1, .markdown-content h2, .markdown-content h3 {{
    margin-top: 24px;
    margin-bottom: 12px;
    font-weight: 600;
    color: {theme['text_primary']};
}}

.markdown-content p {{
    margin-bottom: 12px;
}}

.markdown-content ul, .markdown-content ol {{
    margin-left: 20px;
    margin-bottom: 12px;
}}

.markdown-content li {{
    margin-bottom: 6px;
}}

.markdown-content blockquote {{
    border-left: 3px solid {theme['accent']};
    padding-left: 16px;
    margin: 16px 0;
    color: {theme['text_secondary']};
    font-style: italic;
}}

.markdown-content a {{
    color: {theme['accent']};
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: border-color 0.2s ease;
}}

.markdown-content a:hover {{
    border-bottom-color: {theme['accent']};
}}

/* Smooth Transitions */
* {{
    transition-property: background-color, border-color, color, fill, stroke;
    transition-duration: 0.2s;
    transition-timing-function: ease;
}}

/* Focus Rings */
*:focus-visible {{
    outline: 2px solid {theme['accent']};
    outline-offset: 2px;
}}

/* Selection */
::selection {{
    background: {theme['accent_soft']};
    color: {theme['text_primary']};
}}
    """
