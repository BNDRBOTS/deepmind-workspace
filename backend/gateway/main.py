from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="BNDR::ON Gateway",
    version="1.0.0",
    description="Enterprise API Gateway - Railway Deployment"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SERVICES = {
    "chat": os.getenv("CHAT_SERVICE_URL", "http://localhost:8001"),
    "memory": os.getenv("MEMORY_SERVICE_URL", "http://localhost:8004"),
    "api": os.getenv("API_SERVICE_URL", "http://localhost:8007"),
    "auth": os.getenv("AUTH_SERVICE_URL", "http://localhost:8015"),
}

@app.get("/health")
async def health():
    service_health = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in SERVICES.items():
            try:
                response = await client.get(f"{url}/health")
                service_health[name] = "online" if response.status_code == 200 else "degraded"
            except:
                service_health[name] = "offline"
    
    return {
        "status": "operational",
        "gateway": "online",
        "services": service_health,
        "platform": "railway"
    }

@app.get("/")
async def root():
    return {
        "service": "BNDR::ON Gateway",
        "version": "1.0.0",
        "platform": "Railway",
        "services": list(SERVICES.keys())
    }

@app.api_route("/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def gateway_route(service: str, path: str, request: Request):
    if service not in SERVICES:
        raise HTTPException(404, f"Service '{service}' not found")
    
    service_url = f"{SERVICES[service]}/{path}"
    logger.info(f"Routing {request.method} to {service_url}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.request(
                method=request.method,
                url=service_url,
                content=await request.body(),
                headers={k: v for k, v in request.headers.items() if k.lower() != 'host'},
            )
            
            return JSONResponse(
                content=response.json() if response.headers.get("content-type", "").startswith("application/json") else {"data": response.text},
                status_code=response.status_code
            )
        except httpx.TimeoutException:
            raise HTTPException(504, "Service timeout")
        except httpx.RequestError as e:
            logger.error(f"Service error: {str(e)}")
            raise HTTPException(503, f"Service unavailable: {str(e)}")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )