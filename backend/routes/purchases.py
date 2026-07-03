from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.deps import require_auth
from money.operations import execute_purchase
from routes.articles import find_article_or_404, has_purchased, reject_hidden_draft

router = APIRouter()


class PurchaseBody(BaseModel):
    article_id: str


#--- routes ---

@router.post("/purchases")
async def purchase_article(body: PurchaseBody, user=Depends(require_auth)):
    article = await find_article_or_404(body.article_id)
    reject_hidden_draft(article, user)
    reject_self_purchase(article, user)
    reject_unpublished(article)
    await reject_already_owned(user, article)

    result = await execute_purchase(user, article)
    if not result["success"]:
        raise HTTPException(status_code=result["status_code"], detail=result["message"])
    return {"success": True, "message": "Article unlocked"}


#--- guards ---

def reject_self_purchase(article, user):
    if article["author_id"] == user["_id"]:
        raise HTTPException(status_code=409, detail="You wrote this article — it is already yours")


def reject_unpublished(article):
    if article["status"] != "published":
        raise HTTPException(status_code=404, detail="Article not found")


async def reject_already_owned(user, article):
    if await has_purchased(user["_id"], article["_id"]):
        raise HTTPException(status_code=409, detail="You already own this article")
