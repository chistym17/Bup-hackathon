from fastapi import FastAPI

from api.schemas import OptimizeEnergyRequest, OptimizeEnergyResponse
from api.service import EnergyOptimizeService
from helpers.errors import register_exception_handlers
from helpers.logging import get_logger, log_event, setup_logging
import logging

setup_logging()
app = FastAPI()
register_exception_handlers(app)

service = EnergyOptimizeService()
logger = get_logger("api")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeEnergyResponse)
def optimize_energy(payload: OptimizeEnergyRequest) -> OptimizeEnergyResponse:
    log_event(logger, logging.INFO, "request received", scenario_id=payload.scenario_id)
    return service.run(payload)
