"""
Sandboxed Python code execution service.
Executes user-provided Python code in isolated subprocess with timeout and output capture.
"""
import subprocess
import tempfile
import os
import sys
from pathlib import Path
from typing import Dict, Optional
import structlog

log = structlog.get_logger()


class CodeExecutor:
    """Executes Python code in sandboxed subprocess environment."""
    
    def __init__(self, timeout: int = 30, max_output_size: int = 50000):
        """
        Args:
            timeout: Maximum execution time in seconds
            max_output_size: Maximum output length in characters
        """
        self.timeout = timeout
        self.max_output_size = max_output_size
        self.restricted_imports = [
            "os",
            "subprocess",
            "sys",
            "__import__",
            "eval",
            "exec",
            "compile",
            "open",  # File operations restricted
        ]
    
    def execute(self, code: str, safe_mode: bool = True) -> Dict[str, any]:
        """
        Execute Python code and return results.
        
        Args:
            code: Python code string to execute
            safe_mode: If True, applies import restrictions
            
        Returns:
            Dict with keys:
                - success: bool
                - stdout: str (captured output)
                - stderr: str (error output)
                - return_value: any (if code returns something)
                - execution_time: float (seconds)
                - error: str (error message if failed)
        """
        # Security check for restricted imports in safe mode
        if safe_mode and self._contains_restricted_imports(code):
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": "Code contains restricted imports (os, subprocess, sys, etc.)",
                "execution_time": 0.0,
            }
        
        # Create temporary file for code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            temp_file = f.name
            f.write(code)
        
        try:
            # Execute in subprocess
            import time
            start = time.time()
            
            result = subprocess.run(
                [sys.executable, temp_file],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=self._get_safe_env(),
            )
            
            execution_time = time.time() - start
            
            stdout = result.stdout[:self.max_output_size] if result.stdout else ""
            stderr = result.stderr[:self.max_output_size] if result.stderr else ""
            
            success = result.returncode == 0
            
            log.info(
                "code_executed",
                success=success,
                execution_time=execution_time,
                return_code=result.returncode,
            )
            
            return {
                "success": success,
                "stdout": stdout,
                "stderr": stderr,
                "error": stderr if not success else None,
                "execution_time": execution_time,
                "return_code": result.returncode,
            }
        
        except subprocess.TimeoutExpired:
            log.warning("code_execution_timeout", timeout=self.timeout)
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": f"Code execution timed out after {self.timeout} seconds",
                "execution_time": self.timeout,
            }
        
        except Exception as e:
            log.error("code_execution_error", error=str(e))
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "error": f"Execution error: {str(e)}",
                "execution_time": 0.0,
            }
        
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_file)
            except Exception:
                pass
    
    def _contains_restricted_imports(self, code: str) -> bool:
        """Check if code contains restricted imports."""
        code_lower = code.lower()
        for restricted in self.restricted_imports:
            if f"import {restricted}" in code_lower or f"from {restricted}" in code_lower:
                return True
        return False
    
    def _get_safe_env(self) -> dict:
        """Get sanitized environment variables for subprocess."""
        # Minimal safe environment
        return {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "HOME": os.environ.get("HOME", "/tmp"),
            "USER": "sandbox",
        }


# Singleton instance
_executor: Optional[CodeExecutor] = None


def get_code_executor() -> CodeExecutor:
    """Get singleton code executor instance."""
    global _executor
    if _executor is None:
        _executor = CodeExecutor(timeout=30, max_output_size=50000)
    return _executor
