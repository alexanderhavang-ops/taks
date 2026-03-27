from __future__ import annotations

from fastapi import FastAPI

from takctl.web.subsystems import load_subsystems, get_subsystems_status
from takctl.web.core.static_routes import mount_static_routes
from takctl.web.core.auth_routes import mount_auth_routes
from takctl.web.core.debug_routes import mount_debug_routes, install_exception_handlers
from takctl.web.api.onboarding_import import router as onboarding_import_router
from takctl.web.api.llm2_debug import router as llm2_debug_router
from takctl.web.api.llm_config import router as llm_config_router
from takctl.web.api.llm_usage import router as llm_usage_router
from takctl.web.api.martine import router as martine_router
from takctl.web.api.replay import router as replay_router

from takctl.api.health import router as health_router
from takctl.api.meta import router as meta_router
from takctl.api.onboarding import router as onboarding_router
from takctl.api.onboarding_packages import router as onboarding_packages_router
from takctl.api.onboarding_cards_json import router as onboarding_cards_json_router
from takctl.api.onboarding_identity import router as onboarding_identity_router
from takctl.api.onboarding_policies import router as onboarding_policies_router
from takctl.api.onboarding_cards import router as onboarding_cards_router


def create_app() -> FastAPI:
    app = FastAPI(title="takctl-web")

    # subsystems (best-effort)
    load_subsystems(app)

    @app.get("/api/subsystems")
    def api_subsystems():
        return get_subsystems_status()

    # core mounts
    mount_static_routes(app)
    mount_auth_routes(app)
    mount_debug_routes(app)
    install_exception_handlers(app)

    # API routers
    app.include_router(health_router, prefix="/api")
    app.include_router(meta_router, prefix="/api")

    app.include_router(onboarding_router, prefix="/api")
    app.include_router(onboarding_policies_router, prefix="/api")
    app.include_router(onboarding_packages_router, prefix="/api")
    app.include_router(onboarding_cards_json_router, prefix="/api")
    app.include_router(onboarding_identity_router, prefix="/api")
    app.include_router(onboarding_cards_router, prefix="/api")

    app.include_router(onboarding_import_router)
    app.include_router(llm2_debug_router)
    app.include_router(llm_config_router)
    app.include_router(llm_usage_router)
    app.include_router(martine_router)
    app.include_router(replay_router)

    return app
