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
    author_names = await map_author_names(articles)
    owned_ids = await find_purchased_article_ids(user, articles)

    items = []
    for article in articles:
        owned = compute_entitlement(article, user, owned_ids)
        items.append(serialize_teaser(article, author_names, owned))
    return items


@router.get("/articles/mine")
async def list_my_articles(user=Depends(require_auth)):
    articles = await find_articles_by_author(user["_id"])
    stats = await aggregate_sales_stats(user["_id"])

    items = []
    for article in articles:
        items.append(serialize_mine(article, stats))
    return items


@router.get("/articles/all")
async def list_all_articles(user=Depends(require_admin)):
    articles = await find_all_articles()
    author_names = await map_author_names(articles)

    items = []
    for article in articles:
        item = serialize_teaser(article, author_names, owned=True)
        item["status"] = article["status"]
        items.append(item)
    return items


@router.get("/articles/{article_id}")
async def read_article(article_id: str, user=Depends(optional_auth)):
    article = await find_article_or_404(article_id)
    reject_hidden_draft(article, user)

    owned_ids = await find_purchased_article_ids(user, [article])
    owned = compute_entitlement(article, user, owned_ids)
    author_names = await map_author_names([article])
    return serialize_detail(article, author_names, owned, user)


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

def compute_entitlement(article, user, purchased_ids):
    if user is None:
        return False
    if user["is_admin"]:
        return True
    if article["author_id"] == user["_id"]:
        return True
    return article["_id"] in purchased_ids


def reject_hidden_draft(article, user):
    if article["status"] == "published":
        return
    if user is not None and (user["is_admin"] or article["author_id"] == user["_id"]):
        return
    raise HTTPException(status_code=404, detail="Article not found")


def reject_non_author_non_admin(article, user):
    if user["is_admin"]:
        return
    if article["author_id"] == user["_id"]:
        return
    raise HTTPException(status_code=403, detail="Not your article")


#--- queries ---

async def find_published_articles():
    try:
        cursor = get_db().articles.find({"status": "published"}).sort("created_at", -1)
        return await cursor.to_list(None)
    except Exception as e:
        print(f"MONGO ERROR LISTING ARTICLES: {e}")
        raise HTTPException(status_code=500, detail="Failed to load articles")


async def find_all_articles():
    try:
        cursor = get_db().articles.find({}).sort("created_at", -1)
        return await cursor.to_list(None)
    except Exception as e:
        print(f"MONGO ERROR LISTING ALL ARTICLES: {e}")
        raise HTTPException(status_code=500, detail="Failed to load articles")


async def find_articles_by_author(author_id):
    try:
        cursor = get_db().articles.find({"author_id": author_id}).sort("created_at", -1)
        return await cursor.to_list(None)
    except Exception as e:
        print(f"MONGO ERROR LISTING AUTHOR ARTICLES {author_id}: {e}")
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
        return {}

    names = {}
    for author in authors:
        names[author["_id"]] = author["display_name"]
    return names


async def find_purchased_article_ids(user, articles):
    if user is None or not articles:
        return set()

    article_ids = [article["_id"] for article in articles]
    try:
        cursor = get_db().purchases.find(
            {"buyer_id": user["_id"], "article_id": {"$in": article_ids}}, {"article_id": 1}
        )
        purchases = await cursor.to_list(None)
    except Exception as e:
        print(f"MONGO ERROR FINDING PURCHASES for {user['_id']}: {e}")
        return set()

    return {purchase["article_id"] for purchase in purchases}


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
        return {}

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
        await get_db().articles.update_one({"_id": article_id}, {"$set": updates})
    except Exception as e:
        print(f"MONGO ERROR UPDATING ARTICLE {article_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update article")


async def remove_article(article_id):
    try:
        await get_db().articles.delete_one({"_id": article_id})
    except Exception as e:
        print(f"MONGO ERROR DELETING ARTICLE {article_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete article")


#--- validation ---

def validate_create_fields(body):
    return {
        "title": validate_title(body.title),
        "summary": validate_summary(body.summary),
        "body": validate_body_text(body.body),
        "price_cents": validate_price(body.price_cents),
    }


def validate_update_fields(body):
    updates = {}
    if body.title is not None:
        updates["title"] = validate_title(body.title)
    if body.summary is not None:
        updates["summary"] = validate_summary(body.summary)
    if body.body is not None:
        updates["body"] = validate_body_text(body.body)
    if body.price_cents is not None:
        updates["price_cents"] = validate_price(body.price_cents)
    if body.status is not None:
        updates["status"] = validate_status(body.status)

    if not updates:
        raise HTTPException(status_code=422, detail="Nothing to update")
    return updates


def validate_title(title):
    title = title.strip()
    if not title or len(title) > TITLE_MAX_LENGTH:
        raise HTTPException(status_code=422, detail=f"Title must be 1-{TITLE_MAX_LENGTH} characters")
    return title


def validate_summary(summary):
    summary = summary.strip()
    if not summary or len(summary) > SUMMARY_MAX_LENGTH:
        raise HTTPException(status_code=422, detail=f"Summary must be 1-{SUMMARY_MAX_LENGTH} characters")
    return summary


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


def serialize_teaser(article, author_names, owned):
    return {
        "id": str(article["_id"]),
        "title": article["title"],
        "summary": article["summary"],
        "price_cents": article["price_cents"],
        "author_name": author_names.get(article["author_id"], "Unknown"),
        "created_at": article["created_at"].isoformat(),
        "owned": owned,
    }


def serialize_detail(article, author_names, owned, user):
    # The ONLY place `body` is ever serialized (SPEC content invariant).
    item = serialize_teaser(article, author_names, owned)
    if owned:
        item["body"] = article["body"]
    if user is not None and (user["is_admin"] or article["author_id"] == user["_id"]):
        item["status"] = article["status"]
    return item


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
