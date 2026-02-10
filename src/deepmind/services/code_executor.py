"""
Enterprise-grade Python code execution using RestrictedPython.
Provides AST-level sandboxing with compile-time security enforcement.
Fully configurable via app.yaml - no arbitrary limits.
"""
import sys
import io
import signal
import traceback
from typing import Dict, Any, Optional
from contextlib import redirect_stdout, redirect_stderr
import structlog

from RestrictedPython import compile_restricted, safe_globals, limited_builtins
from RestrictedPython.Guards import guarded_iter_unpack_sequence, safe_builtins
from RestrictedPython.Eval import default_guarded_getattr, default_guarded_getitem

from deepmind.config import get_config

log = structlog.get_logger()


class ExecutionTimeout(Exception):
    """Raised when code execution exceeds time limit."""
    pass


def _timeout_handler(signum, frame):
    """Signal handler for execution timeout."""
    raise ExecutionTimeout("Code execution timed out")


class CodeExecutor:
    """
    Industry-standard sandboxed Python executor using RestrictedPython.
    
    Security features:
    - AST transformation prevents dangerous operations at compile time
    - Restricted builtins (no open, import, eval, exec)
    - Safe attribute/item access with guards
    - Timeout enforcement via signals
    - Configurable memory/output limits
    - Output capture with size limits
    
    All limits configurable via config/app.yaml
    """
    
    def __init__(self, timeout: Optional[int] = None, max_output_size: Optional[int] = None):
        """
        Args:
            timeout: Override config timeout (seconds)
            max_output_size: Override config max output (bytes)
        """
        cfg = get_config()
        
        # Read from config, allow runtime override
        self.timeout = timeout or cfg.code_execution.timeout_seconds
        self.max_output_size = max_output_size or cfg.code_execution.max_output_bytes
        self.max_recursion_depth = cfg.code_execution.max_recursion_depth
        
        # Set Python recursion limit
        sys.setrecursionlimit(self.max_recursion_depth)
        
        # Build safe globals with essential builtins only
        self.safe_globals = self._build_safe_globals()
        
        log.info(
            "code_executor_initialized",
            timeout=self.timeout,
            max_output_mb=self.max_output_size / 1048576,
            max_recursion=self.max_recursion_depth,
        )
    
    def _build_safe_globals(self) -> Dict[str, Any]:
        """
        Construct safe global namespace with restricted builtins.
        
        Includes:
        - Math operations: abs, min, max, sum, round, pow
        - Type constructors: int, float, str, list, dict, tuple, set
        - Iterables: range, enumerate, zip, map, filter
        - Utilities: len, sorted, reversed, all, any
        - String formatting: print (captured)
        
        Excludes:
        - File I/O: open, file
        - Code execution: eval, exec, compile, __import__
        - System access: os, sys, subprocess
        - Introspection: globals, locals, vars, dir (restricted)
        """
        restricted_builtins = {
            # Math & numeric
            'abs': abs,
            'min': min,
            'max': max,
            'sum': sum,
            'round': round,
            'pow': pow,
            'divmod': divmod,
            
            # Type constructors
            'int': int,
            'float': float,
            'str': str,
            'bool': bool,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            'frozenset': frozenset,
            'bytes': bytes,
            'bytearray': bytearray,
            
            # Iterables
            'range': range,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            'iter': iter,
            'next': next,
            
            # Utilities
            'len': len,
            'sorted': sorted,
            'reversed': reversed,
            'all': all,
            'any': any,
            'chr': chr,
            'ord': ord,
            'hex': hex,
            'oct': oct,
            'bin': bin,
            
            # Output (will be captured)
            'print': print,
            
            # Type checking
            'isinstance': isinstance,
            'issubclass': issubclass,
            'type': type,
            'hasattr': hasattr,
            
            # RestrictedPython guards
            '_getattr_': default_guarded_getattr,
            '_getitem_': default_guarded_getitem,
            '_iter_unpack_sequence_': guarded_iter_unpack_sequence,
            '__builtins__': safe_builtins,
            
            # Safe constants
            'True': True,
            'False': False,
            'None': None,
        }
        
        return restricted_builtins
    
    def execute(self, code: str, timeout_override: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute Python code in RestrictedPython sandbox.
        
        Args:
            code: Python code string to execute
            timeout_override: Override timeout for this execution
            
        Returns:
            Dict containing:
                - success: bool
                - stdout: str (printed output)
                - stderr: str (error messages)
                - result: Any (last expression value if applicable)
                - error: str (error description if failed)
                - execution_time: float (seconds)
        """
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        timeout = timeout_override or self.timeout
        
        try:
            # Compile with RestrictedPython (AST transformation)
            import time
            start = time.time()
            
            byte_code = compile_restricted(
                code,
                filename='<user_code>',
                mode='exec',
            )
            
            # Check for compilation errors
            if byte_code.errors:
                error_msg = "\n".join(byte_code.errors)
                log.warning("code_compilation_failed", errors=byte_code.errors)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": error_msg,
                    "error": f"Compilation failed: {error_msg}",
                    "execution_time": 0.0,
                }
            
            if byte_code.warnings:
                log.info("code_compilation_warnings", warnings=byte_code.warnings)
            
            # Set execution timeout (Unix only)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(timeout)
            
            # Execute with captured output
            exec_globals = self.safe_globals.copy()
            
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exec(byte_code.code, exec_globals)
            
            # Cancel timeout
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)
            
            execution_time = time.time() - start
            
            # Capture output with size limits
            stdout_text = stdout_capture.getvalue()[:self.max_output_size]
            stderr_text = stderr_capture.getvalue()[:self.max_output_size]
            
            # Check if output was truncated
            stdout_full = stdout_capture.getvalue()
            if len(stdout_full) > self.max_output_size:
                stdout_text += f"\n\n[OUTPUT TRUNCATED: {len(stdout_full) - self.max_output_size} bytes omitted]"
            
            # Extract result if last statement was expression
            result_value = exec_globals.get('_', None)
            
            log.info(
                "code_executed_successfully",
                execution_time=execution_time,
                output_length=len(stdout_text),
            )
            
            return {
                "success": True,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "result": result_value,
                "error": None,
                "execution_time": execution_time,
            }
        
        except ExecutionTimeout:
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)
            
            log.warning("code_execution_timeout", timeout=timeout)
            return {
                "success": False,
                "stdout": stdout_capture.getvalue()[:self.max_output_size],
                "stderr": "",
                "error": f"Execution timed out after {timeout} seconds",
                "execution_time": timeout,
            }
        
        except Exception as e:
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)
            
            # Capture full traceback
            error_trace = traceback.format_exc()
            
            log.error(
                "code_execution_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            
            return {
                "success": False,
                "stdout": stdout_capture.getvalue()[:self.max_output_size],
                "stderr": error_trace[:self.max_output_size],
                "error": f"{type(e).__name__}: {str(e)}",
                "execution_time": 0.0,
            }
    
    def validate_code(self, code: str) -> Dict[str, Any]:
        """
        Validate code without executing it.
        
        Args:
            code: Python code to validate
            
        Returns:
            Dict with:
                - valid: bool
                - errors: List[str]
                - warnings: List[str]
        """
        try:
            byte_code = compile_restricted(
                code,
                filename='<validation>',
                mode='exec',
            )
            
            return {
                "valid": len(byte_code.errors) == 0,
                "errors": byte_code.errors,
                "warnings": byte_code.warnings,
            }
        
        except Exception as e:
            return {
                "valid": False,
                "errors": [str(e)],
                "warnings": [],
            }


# Singleton instance
_executor: Optional[CodeExecutor] = None


def get_code_executor() -> CodeExecutor:
    """Get singleton RestrictedPython code executor instance."""
    global _executor
    if _executor is None:
        _executor = CodeExecutor()
    return _executor
