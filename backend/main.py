from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.hello import router as hello_router
from db.connection import verify_db_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    await verify_db_connection()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(hello_router)
