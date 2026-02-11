"""
Network Isolation for Code Execution.

Context manager that blocks all network access during code execution by
patching sys.modules with stub modules that raise SecurityError.

Blocks:
- socket (TCP/UDP/DNS)
- urllib, urllib.request (standard library HTTP)
- urllib3 (low-level HTTP)
- httpx (modern async HTTP client)
- requests (popular HTTP library)

Usage:
    with NetworkBlocker():
        exec(user_code)  # Any network operation raises SecurityError
"""
import sys
import structlog
from typing import Dict, Any, Optional
from types import ModuleType

log = structlog.get_logger()


class SecurityError(Exception):
    """Raised when code attempts network access in restricted execution."""
    pass


class NetworkBlocker:
    """
    Context manager that blocks all network access during code execution.
    
    Patches sys.modules to replace network-capable modules with stubs that
    raise SecurityError. Properly restores original modules on exit.
    
    Example:
        with NetworkBlocker():
            # This code cannot make network requests
            exec(untrusted_code, globals_dict)
    """
    
    def __init__(self):
        self._original_modules: Dict[str, Optional[ModuleType]] = {}
        self._modules_to_block = [
            'socket',
            'urllib',
            'urllib.request',
            'urllib.parse',
            'urllib.error',
            'urllib3',
            'httpx',
            'requests',
            'http',
            'http.client',
            'ftplib',
            'smtplib',
            'telnetlib',
            'xmlrpc',
            'xmlrpc.client',
        ]
    
    def __enter__(self):
        """Save original modules and replace with stubs that raise SecurityError."""
        log.info("network_blocker_activated", modules_count=len(self._modules_to_block))
        
        for module_name in self._modules_to_block:
            # Save original module (may be None if not imported yet)
            self._original_modules[module_name] = sys.modules.get(module_name)
            
            # Replace with stub module
            stub = self._create_stub_module(module_name)
            sys.modules[module_name] = stub
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore original modules."""
        for module_name, original_module in self._original_modules.items():
            if original_module is None:
                # Module wasn't imported before, remove our stub
                sys.modules.pop(module_name, None)
            else:
                # Restore original module
                sys.modules[module_name] = original_module
        
        log.info("network_blocker_deactivated", modules_restored=len(self._original_modules))
        
        # Don't suppress exceptions
        return False
    
    def _create_stub_module(self, module_name: str) -> ModuleType:
        """
        Create a stub module that raises SecurityError on attribute access.
        
        The stub intercepts:
        - Direct calls: socket.socket()
        - From imports: from socket import socket
        - Attribute access: socket.AF_INET
        """
        stub = ModuleType(module_name)
        stub.__dict__['__all__'] = []
        stub.__dict__['__file__'] = f'<blocked:{module_name}>'
        
        # Create a custom __getattr__ that blocks all access
        def _blocked_getattr(name: str):
            error_msg = (
                f"Network access is blocked in code execution sandbox. "
                f"Attempted to access '{module_name}.{name}'. "
                f"Remove all network operations from your code."
            )
            
            log.warning(
                "network_access_blocked",
                module=module_name,
                attribute=name,
                blocked_operation=f"{module_name}.{name}",
            )
            
            raise SecurityError(error_msg)
        
        stub.__getattr__ = _blocked_getattr
        
        # Also block common operations that might be directly accessed
        # This handles: from socket import socket
        common_blocked_attrs = [
            'socket', 'create_connection', 'getaddrinfo', 'gethostbyname',
            'urlopen', 'Request', 'HTTPConnection', 'HTTPSConnection',
            'get', 'post', 'put', 'delete', 'Client', 'AsyncClient',
        ]
        
        for attr in common_blocked_attrs:
            stub.__dict__[attr] = lambda *args, **kwargs: _blocked_getattr(attr)
        
        return stub


def create_network_blocked_context():
    """
    Factory function to create NetworkBlocker context manager.
    
    Returns:
        NetworkBlocker instance ready to use as context manager
    """
    return NetworkBlocker()
