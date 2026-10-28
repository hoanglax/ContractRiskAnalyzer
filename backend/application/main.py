
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from application import env, logs
from application.api import analyses
from application.modules.legal_basis import basis

env.load()
logs.setup()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # in a thread: the server answers at once, and the first analysis does not pay for loading the embedder
    threading.Thread(target=basis.warm, daemon=True).start()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Contract Risk Analyzer API",
    version="0.1.0",
    description="API for analyzing risks in contracts.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyses.router)
app.include_router(analyses.demo)


@app.get("/health")
def health_check():
    return {"status": "ok"}
