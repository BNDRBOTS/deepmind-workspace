"""
Network Isolation Tests — Chunk 1.3

Verifies that NetworkBlocker successfully blocks all network operations
during code execution while allowing legitimate computation.
"""
import sys
import pytest
import structlog
from io import StringIO

from deepmind.services.network_blocker import NetworkBlocker, SecurityError
from deepmind.services.code_executor import get_code_executor


class TestNetworkBlocker:
    """Test NetworkBlocker context manager in isolation."""
    
    def test_blocks_socket_import(self):
        """socket module should be blocked and raise SecurityError."""
        with NetworkBlocker():
            with pytest.raises(SecurityError, match="Network access is blocked"):
                import socket
                _ = socket.socket
    
    def test_blocks_socket_creation(self):
        """Creating a socket should raise SecurityError."""
        with NetworkBlocker():
            with pytest.raises(SecurityError, match="socket.socket"):
                import socket
                socket.socket()
    
    def test_blocks_urllib_request(self):
        """urllib.request operations should be blocked."""
        with NetworkBlocker():
            with pytest.raises(SecurityError, match="Network access is blocked"):
                import urllib.request
                urllib.request.urlopen
    
    def test_blocks_http_client(self):
        """http.client operations should be blocked."""
        with NetworkBlocker():
            with pytest.raises(SecurityError, match="Network access is blocked"):
                import http.client
                http.client.HTTPConnection
    
    def test_blocks_httpx_if_installed(self):
        """httpx.get() should be blocked if httpx is installed."""
        try:
            import httpx as _  # Check if installed
            with NetworkBlocker():
                with pytest.raises(SecurityError, match="Network access is blocked"):
                    import httpx
                    httpx.get
        except ImportError:
            pytest.skip("httpx not installed")
    
    def test_blocks_requests_if_installed(self):
        """requests.get() should be blocked if requests is installed."""
        try:
            import requests as _  # Check if installed
            with NetworkBlocker():
                with pytest.raises(SecurityError, match="Network access is blocked"):
                    import requests
                    requests.get
        except ImportError:
            pytest.skip("requests not installed")
    
    def test_restores_modules_after_exit(self):
        """Original modules should be restored after context exit."""
        # Save original socket module
        original_socket = sys.modules.get('socket')
        
        with NetworkBlocker():
            # Inside context, socket is blocked
            blocked_socket = sys.modules.get('socket')
            assert blocked_socket is not original_socket
        
        # After exit, original should be restored
        restored_socket = sys.modules.get('socket')
        if original_socket is None:
            assert restored_socket is None
        else:
            assert restored_socket is original_socket
    
    def test_handles_from_import(self):
        """'from socket import socket' should also be blocked."""
        with NetworkBlocker():
            with pytest.raises(SecurityError):
                from socket import socket as sock_func
                sock_func()
    
    def test_logs_blocked_attempts(self, caplog):
        """Blocked network attempts should be logged."""
        with NetworkBlocker():
            try:
                import socket
                socket.socket()
            except SecurityError:
                pass
        
        # Check that warning was logged
        assert any("network_access_blocked" in rec.message for rec in caplog.records)
    
    def test_allows_non_network_operations(self):
        """Non-network code should work normally inside context."""
        with NetworkBlocker():
            # Math operations should work
            result = 2 + 2
            assert result == 4
            
            # List comprehensions should work
            squares = [x**2 for x in range(10)]
            assert squares == [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]
            
            # String operations should work
            text = "hello world".upper()
            assert text == "HELLO WORLD"


class TestCodeExecutorNetworkIsolation:
    """Test CodeExecutor integration with NetworkBlocker."""
    
    def test_executor_blocks_socket_in_code(self):
        """Code execution should block socket operations."""
        executor = get_code_executor()
        
        code = """
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('example.com', 80))
"""
        
        result = executor.execute(code)
        
        assert result["success"] is False
        assert "SecurityError" in result["error"] or "Network access is blocked" in result["stderr"]
    
    def test_executor_blocks_urllib_in_code(self):
        """Code execution should block urllib operations."""
        executor = get_code_executor()
        
        code = """
import urllib.request
response = urllib.request.urlopen('https://example.com')
"""
        
        result = executor.execute(code)
        
        assert result["success"] is False
        assert "SecurityError" in result["error"] or "Network access is blocked" in result["stderr"]
    
    def test_executor_blocks_httpx_in_code(self):
        """Code execution should block httpx if available."""
        executor = get_code_executor()
        
        code = """
try:
    import httpx
    client = httpx.Client()
    response = client.get('https://example.com')
except ImportError:
    print('httpx not installed')
"""
        
        result = executor.execute(code)
        
        # If httpx not installed, that's fine
        if "httpx not installed" in result["stdout"]:
            pytest.skip("httpx not installed")
        
        # If httpx IS installed, it should be blocked
        assert result["success"] is False
        assert "SecurityError" in result["error"] or "Network access is blocked" in result["stderr"]
    
    def test_executor_allows_safe_code(self):
        """Non-network code should execute successfully."""
        executor = get_code_executor()
        
        code = """
# Math and data processing
import math

data = [1, 2, 3, 4, 5]
squares = [x**2 for x in data]
total = sum(squares)
average = total / len(squares)

print(f"Squares: {squares}")
print(f"Total: {total}")
print(f"Average: {average}")

result = math.sqrt(total)
print(f"Square root of total: {result}")
"""
        
        result = executor.execute(code)
        
        assert result["success"] is True
        assert "Squares: [1, 4, 9, 16, 25]" in result["stdout"]
        assert "Total: 55" in result["stdout"]
    
    def test_executor_blocks_dns_resolution(self):
        """DNS resolution operations should be blocked."""
        executor = get_code_executor()
        
        code = """
import socket
ip = socket.gethostbyname('example.com')
print(f"IP: {ip}")
"""
        
        result = executor.execute(code)
        
        assert result["success"] is False
        assert "SecurityError" in result["error"] or "Network access is blocked" in result["stderr"]
    
    def test_multiple_executions_maintain_isolation(self):
        """Multiple executions should each be properly isolated."""
        executor = get_code_executor()
        
        # First execution - blocked network code
        result1 = executor.execute("import socket; socket.socket()")
        assert result1["success"] is False
        
        # Second execution - safe code
        result2 = executor.execute("print(2 + 2)")
        assert result2["success"] is True
        assert "4" in result2["stdout"]
        
        # Third execution - blocked network code again
        result3 = executor.execute("import urllib.request; urllib.request.urlopen('http://x.com')")
        assert result3["success"] is False


class TestNetworkBlockerEdgeCases:
    """Test edge cases and corner scenarios."""
    
    def test_nested_module_access(self):
        """Nested module attributes should be blocked."""
        with NetworkBlocker():
            with pytest.raises(SecurityError):
                import urllib.request
                urllib.request.Request
    
    def test_module_not_previously_imported(self):
        """Blocking should work even if module wasn't imported before."""
        # Ensure ftplib isn't imported
        if 'ftplib' in sys.modules:
            del sys.modules['ftplib']
        
        with NetworkBlocker():
            with pytest.raises(SecurityError):
                import ftplib
                ftplib.FTP
    
    def test_exception_in_context_restores_modules(self):
        """Modules should be restored even if exception occurs."""
        original_socket = sys.modules.get('socket')
        
        try:
            with NetworkBlocker():
                # Cause an exception
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # Modules should still be restored
        restored_socket = sys.modules.get('socket')
        if original_socket is None:
            assert restored_socket is None
        else:
            assert restored_socket is original_socket


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
