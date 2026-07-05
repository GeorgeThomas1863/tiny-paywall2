from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.deps import require_auth
from db.connection import get_db
from routes.articles import aggregate_scores, find_article_or_404

router = APIRouter()

VOTE_VALUES = (1, -1, 0)


class VoteBody(BaseModel):
    value: int


#--- routes ---

@router.put("/articles/{article_id}/vote")
async def set_vote(article_id: str, body: VoteBody, user=Depends(require_auth)):
    article = await find_article_or_404(article_id)
    value = validate_vote_value(body.value)

    await apply_vote_to_purchase(user["_id"], article["_id"], value)
    score = await fetch_article_score(article["_id"])

    message = "Vote cleared" if value == 0 else "Vote recorded"
    return {"success": True, "message": message, "score": score, "my_vote": value}


#--- operations ---

async def apply_vote_to_purchase(buyer_id, article_id, value):
    update = {"$set": {"vote": value}} if value else {"$unset": {"vote": ""}}
    try:
        result = await get_db().purchases.update_one(
            {"buyer_id": buyer_id, "article_id": article_id}, update
        )
    except Exception as e:
        print(f"MONGO ERROR APPLYING VOTE {buyer_id}/{article_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to record vote")

    if result.matched_count == 0:
        raise HTTPException(status_code=403, detail="Only buyers can vote")


#--- queries ---

async def fetch_article_score(article_id):
    scores = await aggregate_scores([article_id])
    return scores.get(article_id, 0)


#--- validation ---

def validate_vote_value(value):
    if value not in VOTE_VALUES:
        raise HTTPException(status_code=422, detail="Vote must be 1, -1, or 0")
    return value
