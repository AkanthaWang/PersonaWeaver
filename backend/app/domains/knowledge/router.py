from fastapi import APIRouter, Depends, Query, status

from backend.app.core.dependencies import current_user, get_db

from .schemas import CharacterCreate, CharacterUpdate, ClueCreate, ClueUpdate, EventCreate, EventUpdate, FactCreate, FactUpdate, RelationCreate, RelationUpdate, ReviewResolution
from .service import KnowledgeService

router = APIRouter()


def service(db):
    return KnowledgeService(db)


@router.get("/books/{book_id}/knowledge/characters")
def characters(book_id: str, user=Depends(current_user), db=Depends(get_db)):
    return service(db).characters(user["user_id"], book_id)


@router.post("/books/{book_id}/knowledge/characters", status_code=status.HTTP_201_CREATED)
def create_character(book_id: str, payload: CharacterCreate, user=Depends(current_user), db=Depends(get_db)):
    return service(db).create_character(user["user_id"], book_id, payload)


@router.patch("/books/{book_id}/knowledge/characters/{character_id}")
def update_character(book_id: str, character_id: str, payload: CharacterUpdate, user=Depends(current_user), db=Depends(get_db)):
    return service(db).update_character(user["user_id"], book_id, character_id, payload)


@router.delete("/books/{book_id}/knowledge/characters/{character_id}")
def delete_character(book_id: str, character_id: str, reason: str = Query(default=""), user=Depends(current_user), db=Depends(get_db)):
    return service(db).delete_character(user["user_id"], book_id, character_id, reason)


@router.post("/books/{book_id}/knowledge/characters/{character_id}/restore")
def restore_character(book_id: str, character_id: str, user=Depends(current_user), db=Depends(get_db)):
    return service(db).restore_character(user["user_id"], book_id, character_id)


@router.get("/books/{book_id}/knowledge/characters/{character_id}/facts")
def facts(book_id: str, character_id: str, user=Depends(current_user), db=Depends(get_db)):
    return service(db).facts(user["user_id"], book_id, character_id)


@router.post("/books/{book_id}/knowledge/facts", status_code=status.HTTP_201_CREATED)
def create_fact(book_id: str, payload: FactCreate, user=Depends(current_user), db=Depends(get_db)):
    return service(db).create_fact(user["user_id"], book_id, payload)


@router.patch("/books/{book_id}/knowledge/facts/{fact_id}")
def update_fact(book_id: str, fact_id: str, payload: FactUpdate, user=Depends(current_user), db=Depends(get_db)):
    return service(db).update_fact(user["user_id"], book_id, fact_id, payload)


@router.delete("/books/{book_id}/knowledge/facts/{fact_id}")
def delete_fact(book_id: str, fact_id: str, reason: str = Query(default=""), user=Depends(current_user), db=Depends(get_db)):
    return service(db).delete_fact(user["user_id"], book_id, fact_id, reason)


@router.get("/books/{book_id}/knowledge/clues")
def clues(book_id: str, user=Depends(current_user), db=Depends(get_db)):
    return service(db).clues(user["user_id"], book_id)


@router.post("/books/{book_id}/knowledge/clues", status_code=status.HTTP_201_CREATED)
def create_clue(book_id: str, payload: ClueCreate, user=Depends(current_user), db=Depends(get_db)):
    return service(db).create_clue(user["user_id"], book_id, payload)


@router.patch("/books/{book_id}/knowledge/clues/{clue_id}")
def update_clue(book_id: str, clue_id: str, payload: ClueUpdate, user=Depends(current_user), db=Depends(get_db)):
    return service(db).update_clue(user["user_id"], book_id, clue_id, payload)


@router.delete("/books/{book_id}/knowledge/clues/{clue_id}")
def delete_clue(book_id: str, clue_id: str, reason: str = Query(default=""), user=Depends(current_user), db=Depends(get_db)):
    return service(db).delete_clue(user["user_id"], book_id, clue_id, reason)


@router.post("/books/{book_id}/knowledge/clues/{clue_id}/verify")
def verify_clue(book_id: str, clue_id: str, reason: str = Query(default=""), user=Depends(current_user), db=Depends(get_db)):
    return service(db).verify_clue(user["user_id"], book_id, clue_id, reason)


@router.get("/books/{book_id}/knowledge/events")
def events(book_id: str, user=Depends(current_user), db=Depends(get_db)):
    return service(db).events(user["user_id"], book_id)


@router.post("/books/{book_id}/knowledge/events", status_code=status.HTTP_201_CREATED)
def create_event(book_id: str, payload: EventCreate, user=Depends(current_user), db=Depends(get_db)):
    return service(db).create_event(user["user_id"], book_id, payload)


@router.patch("/books/{book_id}/knowledge/events/{event_id}")
def update_event(book_id: str, event_id: str, payload: EventUpdate, user=Depends(current_user), db=Depends(get_db)):
    return service(db).update_event(user["user_id"], book_id, event_id, payload)


@router.delete("/books/{book_id}/knowledge/events/{event_id}")
def delete_event(book_id: str, event_id: str, reason: str = Query(default=""), user=Depends(current_user), db=Depends(get_db)):
    return service(db).delete_event(user["user_id"], book_id, event_id, reason)


@router.get("/books/{book_id}/knowledge/changes")
def changes(book_id: str, limit: int = Query(default=100, ge=1, le=500), user=Depends(current_user), db=Depends(get_db)):
    return service(db).changes(user["user_id"], book_id, limit)


@router.get("/books/{book_id}/knowledge/relations")
def relations(book_id: str, user=Depends(current_user), db=Depends(get_db)):
    return service(db).relations(user["user_id"], book_id)


@router.post("/books/{book_id}/knowledge/relations", status_code=status.HTTP_201_CREATED)
def create_relation(book_id: str, payload: RelationCreate, user=Depends(current_user), db=Depends(get_db)):
    return service(db).create_relation(user["user_id"], book_id, payload)


@router.patch("/books/{book_id}/knowledge/relations/{relation_id}")
def update_relation(book_id: str, relation_id: str, payload: RelationUpdate, user=Depends(current_user), db=Depends(get_db)):
    return service(db).update_relation(user["user_id"], book_id, relation_id, payload)


@router.delete("/books/{book_id}/knowledge/relations/{relation_id}")
def delete_relation(book_id: str, relation_id: str, reason: str = Query(default=""), user=Depends(current_user), db=Depends(get_db)):
    return service(db).delete_relation(user["user_id"], book_id, relation_id, reason)


@router.post("/books/{book_id}/knowledge/characters/{source_id}/merge/{target_id}")
def merge_characters(book_id: str, source_id: str, target_id: str, reason: str = Query(default=""), user=Depends(current_user), db=Depends(get_db)):
    return service(db).merge_characters(user["user_id"], book_id, source_id, target_id, reason)


@router.post("/books/{book_id}/knowledge/merges/{merge_id}/restore")
def unmerge_character(book_id: str, merge_id: str, user=Depends(current_user), db=Depends(get_db)):
    return service(db).unmerge_character(user["user_id"], book_id, merge_id)


@router.get("/books/{book_id}/knowledge/reviews")
def reviews(book_id: str, state: str = Query(default="pending"), user=Depends(current_user), db=Depends(get_db)):
    return service(db).reviews(user["user_id"], book_id, state)


@router.post("/books/{book_id}/knowledge/reviews/{review_id}/resolve")
def resolve_review(book_id: str, review_id: str, payload: ReviewResolution, user=Depends(current_user), db=Depends(get_db)):
    return service(db).resolve_review(user["user_id"], book_id, review_id, payload)


@router.post("/books/{book_id}/knowledge/batches/{batch_id}/rollback")
def rollback_batch(book_id: str, batch_id: str, reason: str = Query(default=""), user=Depends(current_user), db=Depends(get_db)):
    return service(db).rollback_batch(user["user_id"], book_id, batch_id, reason)
