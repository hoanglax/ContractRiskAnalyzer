
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from application import logs
from application.api import analyses

logs.setup()

app = FastAPI(
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
