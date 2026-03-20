from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import topics, content, user, reminder


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create all DB tables
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown: nothing to clean up for now


app = FastAPI(
    title="顺发 API",
    description="Gamified writing assistant backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(topics.router, prefix="/api")
app.include_router(content.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(reminder.router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/")
async def root():
    return {"message": "顺发 API", "docs": "/docs"}
