from fastapi import FastAPI

from takctl.api.health import router as health_router

app = FastAPI(title="takctl-web")
app.include_router(health_router, prefix="/api")
