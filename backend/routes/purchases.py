from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.deps import require_auth
from money.operations import execute_purchase
from routes.articles import find_article_or_404

router = APIRouter()


class PurchaseBody(BaseModel):
    article_id: str


#--- routes ---

@router.post("/purchases")
async def purchase_article(body: PurchaseBody, user=Depends(require_auth)):
    # Guard order per SPEC §2.4: exists & published → not the author → transaction
    # (the transaction itself enforces balance and not-already-owned atomically).
    article = await find_article_or_404(body.article_id)
    reject_unpublished(article)
    reject_self_purchase(article, user)

    result = await execute_purchase(user, article)
    if not result["success"]:
        raise HTTPException(status_code=result["status_code"], detail=result["message"])
    return result


#--- guards ---

def reject_unpublished(article):
    if article["status"] != "published":
        raise HTTPException(status_code=404, detail="Article not found")


def reject_self_purchase(article, user):
    if article["author_id"] == user["_id"]:
        raise HTTPException(status_code=409, detail="You wrote this article — it is already yours")
