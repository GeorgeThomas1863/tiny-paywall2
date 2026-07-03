from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from config import get_backend_port, get_frontend_url
from db.connection import verify_db_connection, ensure_indexes
from routes.articles import router as articles_router
from routes.auth import router as auth_router
from routes.hello import router as hello_router
from routes.purchases import router as purchases_router
from routes.stripe_webhook import router as stripe_webhook_router
from routes.wallet import router as wallet_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await verify_db_connection()
    await ensure_indexes()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_frontend_url()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(articles_router)
app.include_router(wallet_router)
app.include_router(purchases_router)
app.include_router(stripe_webhook_router)
app.include_router(hello_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", reload=True, port=get_backend_port())
