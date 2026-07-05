import asyncio
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.deps import optional_auth, require_admin, require_auth
from db.connection import get_db

router = APIRouter()

TITLE_MAX_LENGTH = 200
SUMMARY_MAX_LENGTH = 1000
PRICE_MIN_CENTS = 1
PRICE_MAX_CENTS = 500
ARTICLE_STATUSES = ("draft", "published")


class ArticleCreateBody(BaseModel):
    title: str
    summary: str
    body: str
    price_cents: int


class ArticleUpdateBody(BaseModel):
    title: str | None = None
    summary: str | None = None
    body: str | None = None
    price_cents: int | None = None
    status: str | None = None


#--- routes ---

@router.get("/articles")
async def list_articles(user=Depends(optional_auth)):
    articles = await find_published_articles()
    article_ids = [article["_id"] for article in articles]
    author_names, purchased_ids, scores = await asyncio.gather(
        map_author_names(articles),
        find_purchased_article_ids(user, articles),
        aggregate_scores(article_ids),
    )

    items = []
    for article in articles:
        owned = is_author_or_admin(article, user) or article["_id"] in purchased_ids
        items.append(serialize_teaser(article, author_names, owned, scores))
    return items


@router.get("/articles/mine")
async def list_my_articles(user=Depends(require_auth)):
    articles, stats = await asyncio.gather(
        find_articles_by_author(user["_id"]), aggregate_sales_stats(user["_id"])
    )

    items = []
    for article in articles:
        items.append(serialize_mine(article, stats))
    return items


@router.get("/articles/all")
async def list_all_articles(user=Depends(require_admin)):
    articles = await find_all_articles()
    article_ids = [article["_id"] for article in articles]
    author_names, scores = await asyncio.gather(
        map_author_names(articles), aggregate_scores(article_ids)
    )

    items = []
    for article in articles:
        items.append(serialize_admin_teaser(article, author_names, scores))
    return items


@router.get("/articles/{article_id}")
async def read_article(article_id: str, user=Depends(optional_auth)):
    article = await find_article_or_404(article_id)
    reject_hidden_draft(article, user)

    purchase, author_names, scores = await asyncio.gather(
        find_purchase(user, article["_id"]),
        map_author_names([article]),
        aggregate_scores([article["_id"]]),
    )
    owned = is_author_or_admin(article, user) or purchase is not None
    return serialize_detail(article, author_names, owned, user, scores, purchase)


@router.post("/articles")
async def create_article(body: ArticleCreateBody, user=Depends(require_auth)):
    fields = validate_create_fields(body)
    article_doc = build_article_doc(user["_id"], fields)

    article_id = await insert_article(article_doc)
    return {"success": True, "message": "Article created as draft", "id": article_id}


@router.put("/articles/{article_id}")
async def update_article(article_id: str, body: ArticleUpdateBody, user=Depends(require_auth)):
    article = await find_article_or_404(article_id)
    reject_non_author_non_admin(article, user)

    updates = validate_update_fields(body)
    await apply_article_update(article["_id"], updates)
    return {"success": True, "message": "Article updated"}


@router.delete("/articles/{article_id}")
async def delete_article(article_id: str, user=Depends(require_auth)):
    article = await find_article_or_404(article_id)
    reject_non_author_non_admin(article, user)

    await remove_article(article["_id"])
    return {"success": True, "message": "Article deleted"}


#--- guards / entitlement ---

def is_author_or_admin(article, user):
    if user is None:
        return False
    return user["is_admin"] or article["author_id"] == user["_id"]




def reject_hidden_draft(article, user):
    if article["status"] == "published":
        return
    if is_author_or_admin(article, user):
        return
    raise HTTPException(status_code=404, detail="Article not found")


def reject_non_author_non_admin(article, user):
    if is_author_or_admin(article, user):
        return
    raise HTTPException(status_code=403, detail="Not your article")


#--- queries ---

async def find_published_articles():
    return await find_articles_sorted({"status": "published"})


async def find_all_articles():
    return await find_articles_sorted({})


async def find_articles_by_author(author_id):
    return await find_articles_sorted({"author_id": author_id})


async def find_articles_sorted(query):
    try:
        cursor = get_db().articles.find(query).sort("created_at", -1)
        return await cursor.to_list(None)
    except Exception as e:
        print(f"MONGO ERROR LISTING ARTICLES {query}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load articles")


async def find_article_or_404(article_id):
    object_id = parse_object_id(article_id)
    if object_id is None:
        raise HTTPException(status_code=404, detail="Article not found")

    try:
        article = await get_db().articles.find_one({"_id": object_id})
    except Exception as e:
        print(f"MONGO ERROR FINDING ARTICLE {article_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load article")

    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


async def map_author_names(articles):
    author_ids = list({article["author_id"] for article in articles})
    if not author_ids:
        return {}

    try:
        cursor = get_db().users.find({"_id": {"$in": author_ids}}, {"display_name": 1})
        authors = await cursor.to_list(None)
    except Exception as e:
        print(f"MONGO ERROR MAPPING AUTHOR NAMES: {e}")
        raise HTTPException(status_code=500, detail="Failed to load articles")

    names = {}
    for author in authors:
        names[author["_id"]] = author["display_name"]
    return names


async def find_purchased_article_ids(user, articles):
    if user is None or user["is_admin"] or not articles:
        return set()

    article_ids = [article["_id"] for article in articles]
    try:
        cursor = get_db().purchases.find(
            {"buyer_id": user["_id"], "article_id": {"$in": article_ids}}, {"article_id": 1}
        )
        purchases = await cursor.to_list(None)
    except Exception as e:
        print(f"MONGO ERROR FINDING PURCHASES for {user['_id']}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load articles")

    return {purchase["article_id"] for purchase in purchases}


async def find_purchase(user, article_id):
    if user is None:
        return None

    try:
        return await get_db().purchases.find_one(
            {"buyer_id": user["_id"], "article_id": article_id}
        )
    except Exception as e:
        print(f"MONGO ERROR CHECKING PURCHASE {user['_id']}/{article_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load article")


async def aggregate_scores(article_ids):
    if not article_ids:
        return {}

    pipeline = [
        {"$match": {"article_id": {"$in": article_ids}, "vote": {"$exists": True}}},
        {"$group": {"_id": "$article_id", "score": {"$sum": "$vote"}}},
    ]
    try:
        rows = await get_db().purchases.aggregate(pipeline).to_list(None)
    except Exception as e:
        print(f"MONGO ERROR AGGREGATING SCORES: {e}")
        raise HTTPException(status_code=500, detail="Failed to load scores")

    scores = {}
    for row in rows:
        scores[row["_id"]] = row["score"]
    return scores


async def aggregate_sales_stats(author_id):
    pipeline = [
        {"$match": {"author_id": author_id}},
        {"$group": {
            "_id": "$article_id",
            "sales_count": {"$sum": 1},
            "earned_cents": {"$sum": "$author_cents"},
        }},
    ]
    try:
        rows = await get_db().purchases.aggregate(pipeline).to_list(None)
    except Exception as e:
        print(f"MONGO ERROR AGGREGATING SALES for {author_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load sales stats")

    stats = {}
    for row in rows:
        stats[row["_id"]] = row
    return stats


#--- operations ---

async def insert_article(article_doc):
    try:
        result = await get_db().articles.insert_one(article_doc)
        return str(result.inserted_id)
    except Exception as e:
        print(f"MONGO ERROR INSERTING ARTICLE: {e}")
        raise HTTPException(status_code=500, detail="Failed to create article")


async def apply_article_update(article_id, updates):
    updates["updated_at"] = datetime.now(timezone.utc)
    try:
        result = await get_db().articles.update_one({"_id": article_id}, {"$set": updates})
    except Exception as e:
        print(f"MONGO ERROR UPDATING ARTICLE {article_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update article")

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Article not found")


async def remove_article(article_id):
    try:
        result = await get_db().articles.delete_one({"_id": article_id})
    except Exception as e:
        print(f"MONGO ERROR DELETING ARTICLE {article_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete article")

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Article not found")


#--- validation ---

def validate_create_fields(body):
    return {
        "title": validate_text_field(body.title, "Title", TITLE_MAX_LENGTH),
        "summary": validate_text_field(body.summary, "Summary", SUMMARY_MAX_LENGTH),
        "body": validate_body_text(body.body),
        "price_cents": validate_price(body.price_cents),
    }


def validate_update_fields(body):
    updates = {}
    if body.title is not None:
        updates["title"] = validate_text_field(body.title, "Title", TITLE_MAX_LENGTH)
    if body.summary is not None:
        updates["summary"] = validate_text_field(body.summary, "Summary", SUMMARY_MAX_LENGTH)
    if body.body is not None:
        updates["body"] = validate_body_text(body.body)
    if body.price_cents is not None:
        updates["price_cents"] = validate_price(body.price_cents)
    if body.status is not None:
        updates["status"] = validate_status(body.status)

    if not updates:
        raise HTTPException(status_code=422, detail="Nothing to update")
    return updates


def validate_text_field(value, label, max_length):
    value = value.strip()
    if not value or len(value) > max_length:
        raise HTTPException(status_code=422, detail=f"{label} must be 1-{max_length} characters")
    return value


def validate_body_text(body_text):
    if not body_text.strip():
        raise HTTPException(status_code=422, detail="Body must not be empty")
    return body_text


def validate_price(price_cents):
    if price_cents < PRICE_MIN_CENTS or price_cents > PRICE_MAX_CENTS:
        raise HTTPException(
            status_code=422,
            detail=f"Price must be {PRICE_MIN_CENTS}-{PRICE_MAX_CENTS} cents",
        )
    return price_cents


def validate_status(status):
    if status not in ARTICLE_STATUSES:
        raise HTTPException(status_code=422, detail="Status must be draft or published")
    return status


#--- builders ---

def parse_object_id(article_id):
    try:
        return ObjectId(article_id)
    except (InvalidId, TypeError):
        return None


def build_article_doc(author_id, fields):
    now = datetime.now(timezone.utc)
    return {
        "author_id": author_id,
        "title": fields["title"],
        "summary": fields["summary"],
        "body": fields["body"],
        "price_cents": fields["price_cents"],
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }


def serialize_teaser(article, author_names, owned, scores):
    return {
        "id": str(article["_id"]),
        "title": article["title"],
        "summary": article["summary"],
        "price_cents": article["price_cents"],
        "author_name": author_names.get(article["author_id"], "Unknown"),
        "created_at": article["created_at"].isoformat(),
        "owned": owned,
        "score": scores.get(article["_id"], 0),
    }


def serialize_admin_teaser(article, author_names, scores):
    item = serialize_teaser(article, author_names, True, scores)
    item["status"] = article["status"]
    return item


def serialize_detail(article, author_names, owned, user, scores, purchase):
    # The ONLY place `body` is ever serialized (SPEC content invariant).
    item = serialize_teaser(article, author_names, owned, scores)
    item["my_vote"] = derive_my_vote(purchase)
    if owned:
        item["body"] = article["body"]
    if is_author_or_admin(article, user):
        item["status"] = article["status"]
    return item


def derive_my_vote(purchase):
    if purchase is None:
        return None
    return purchase.get("vote", 0)


def serialize_mine(article, stats):
    article_stats = stats.get(article["_id"], {})
    return {
        "id": str(article["_id"]),
        "title": article["title"],
        "summary": article["summary"],
        "price_cents": article["price_cents"],
        "status": article["status"],
        "created_at": article["created_at"].isoformat(),
        "sales_count": article_stats.get("sales_count", 0),
        "earned_cents": article_stats.get("earned_cents", 0),
    }
