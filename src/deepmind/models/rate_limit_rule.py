"""
Rate Limit Rule Model.

Defines rate limiting configuration for individual endpoints.
Used in config/app.yaml to specify per-route limits.
"""
from typing import Optional
from pydantic import BaseModel, Field


class RateLimitRule(BaseModel):
    """
    Configuration for a single rate limit rule.
    
    Example:
        RateLimitRule(
            endpoint="/api/execute-code",
            limit="10/hour",
            description="Code execution limit"
        )
    """
    endpoint: str = Field(
        ...,
        description="API endpoint path (e.g., '/api/execute-code')"
    )
    
    limit: str = Field(
        ...,
        description="Rate limit string in SlowAPI format (e.g., '10/hour', '60/minute')"
    )
    
    description: Optional[str] = Field(
        None,
        description="Human-readable description of this limit"
    )
    
    per_user: bool = Field(
        True,
        description="If True, limit is per authenticated user. If False, limit is global."
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "endpoint": "/api/execute-code",
                    "limit": "10/hour",
                    "description": "Code execution limit per user",
                    "per_user": True,
                },
                {
                    "endpoint": "/api/generate-image",
                    "limit": "20/hour",
                    "description": "Image generation limit per user",
                    "per_user": True,
                },
            ]
        }
