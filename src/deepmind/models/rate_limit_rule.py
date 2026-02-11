"""
Rate Limit Rule Model.

Defines rate limit rules with parsing logic for limit strings like "10/hour", "60/minute".
Used by rate limiting middleware to enforce per-endpoint and per-user quotas.
"""
from dataclasses import dataclass
from typing import Tuple
import structlog

log = structlog.get_logger()


@dataclass
class RateLimitRule:
    """
    Represents a rate limit rule for an endpoint.
    
    Format: "count/period" where period is: second, minute, hour, day
    Examples:
        - "10/hour" → 10 requests per hour
        - "60/minute" → 60 requests per minute
        - "100/day" → 100 requests per day
        - "5/second" → 5 requests per second
    
    Multiple limits can be combined:
        - "10/hour;100/day" → 10 per hour AND 100 per day
    """
    
    endpoint: str
    limit_string: str
    
    def __post_init__(self):
        """Validate limit string format on initialization."""
        if not self.limit_string:
            raise ValueError(f"Empty limit string for endpoint {self.endpoint}")
        
        # Validate each limit in the string
        for limit_part in self.limit_string.split(';'):
            limit_part = limit_part.strip()
            if '/' not in limit_part:
                raise ValueError(
                    f"Invalid limit format '{limit_part}' for endpoint {self.endpoint}. "
                    f"Expected format: 'count/period' (e.g., '10/hour')"
                )
            
            try:
                count_str, period = limit_part.split('/', 1)
                count = int(count_str.strip())
                period = period.strip().lower()
                
                if count <= 0:
                    raise ValueError(f"Rate count must be positive, got {count}")
                
                if period not in ['second', 'minute', 'hour', 'day']:
                    raise ValueError(
                        f"Invalid period '{period}'. "
                        f"Must be one of: second, minute, hour, day"
                    )
            
            except (ValueError, AttributeError) as e:
                raise ValueError(
                    f"Failed to parse limit '{limit_part}' for endpoint {self.endpoint}: {e}"
                )
    
    def parse_limit(self, limit_part: str) -> Tuple[int, str]:
        """
        Parse a single limit string into (count, period).
        
        Args:
            limit_part: Limit string like "10/hour"
            
        Returns:
            Tuple of (count, period) e.g., (10, "hour")
        """
        count_str, period = limit_part.split('/', 1)
        return int(count_str.strip()), period.strip().lower()
    
    def get_primary_limit(self) -> Tuple[int, str]:
        """
        Get the primary (first) limit from the limit string.
        Used when only one limit needs to be applied.
        
        Returns:
            Tuple of (count, period)
        """
        first_limit = self.limit_string.split(';')[0].strip()
        return self.parse_limit(first_limit)
    
    def get_all_limits(self) -> list[Tuple[int, str]]:
        """
        Get all limits from the limit string.
        Used when multiple stacked limits need to be applied.
        
        Returns:
            List of (count, period) tuples
        """
        limits = []
        for limit_part in self.limit_string.split(';'):
            limit_part = limit_part.strip()
            if limit_part:
                limits.append(self.parse_limit(limit_part))
        return limits
    
    def __str__(self) -> str:
        return f"RateLimitRule(endpoint={self.endpoint}, limit={self.limit_string})"


def parse_rate_limit(limit_string: str) -> Tuple[int, str]:
    """
    Utility function to parse a rate limit string.
    
    Args:
        limit_string: String like "10/hour"
        
    Returns:
        Tuple of (count, period)
        
    Raises:
        ValueError: If format is invalid
    """
    if '/' not in limit_string:
        raise ValueError(
            f"Invalid rate limit format '{limit_string}'. "
            f"Expected 'count/period' (e.g., '10/hour')"
        )
    
    count_str, period = limit_string.split('/', 1)
    
    try:
        count = int(count_str.strip())
    except ValueError:
        raise ValueError(
            f"Invalid count in rate limit '{limit_string}'. "
            f"Count must be an integer."
        )
    
    period = period.strip().lower()
    
    if period not in ['second', 'minute', 'hour', 'day']:
        raise ValueError(
            f"Invalid period '{period}' in rate limit '{limit_string}'. "
            f"Must be one of: second, minute, hour, day"
        )
    
    if count <= 0:
        raise ValueError(
            f"Rate count must be positive in '{limit_string}', got {count}"
        )
    
    return count, period
