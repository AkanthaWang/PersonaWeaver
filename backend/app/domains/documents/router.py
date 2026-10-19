from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from backend.app.core.dependencies import current_user, get_config, get_db
from backend.app.db.database import identifier

from .schemas import ExtractRequest, ResolutionRequest
from .service import SUPPORTED, DocumentService

router = APIRouter()


async def _save_upload(request: Request, target: Path, limit: int):
    size = 0
    try:
        with target.open("wb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"文件大小不能超过 {limit // (1024 * 1024)} MB")
                output.write(chunk)
        if not size:
            raise HTTPException(422, "文件不能为空")
    except Exception:
        target.unlink(missing_ok=True)
        raise


def _filename_parts(filename: str | None) -> tuple[str, str]:
    safe_name = (filename or "").replace("\\", "/").split("/")[-1].strip()
    if not safe_name or len(safe_name) > 255:
        raise HTTPException(422, "文件名不能为空且不能超过 255 个字符")
    suffix = Path(safe_name).suffix.lower().lstrip(".")
    if suffix not in SUPPORTED:
        raise HTTPException(422, "支持 TXT、Markdown、EPUB、PDF 和 DOCX 文件")
    return safe_name, suffix


def _create_uploaded_book(service, user_id, filename, suffix, target, *, title=None, author="", language="zh-CN"):
    book_title = (title or "").strip() or Path(filename).stem
    if not book_title or len(book_title) > 200 or len(author) > 200 or len(language) > 40:
        raise HTTPException(422, "书籍信息长度不合法")
    return service.create(
        user_id, title=book_title, author=author.strip(), language=language,
        filename=filename, suffix=suffix, source_path=target,
    )


async def _save_multipart_upload(
    upload: UploadFile, target: Path, *, file_limit: int, total_before: int, total_limit: int,
) -> tuple[int, str | None]:
    size = 0
    error = None
    try:
        with target.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > file_limit:
                    error = f"文件大小不能超过 {file_limit // (1024 * 1024)} MB"
                    break
                if total_before + size > total_limit:
                    error = f"批量文件总大小不能超过 {total_limit // (1024 * 1024)} MB"
                    break
                output.write(chunk)
        if error:
            target.unlink(missing_ok=True)
        elif not size:
            target.unlink(missing_ok=True)
            error = "文件不能为空"
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return size, error


@router.get("/books")
def list_documents(user=Depends(current_user), db=Depends(get_db)):
    return DocumentService(db).list(user["user_id"])


@router.post("/books", status_code=201)
async def upload_book(
    request: Request, filename: str = Query(max_length=255), title: str = "",
    author: str = "", language: str = "zh-CN",
    user=Depends(current_user), db=Depends(get_db), config=Depends(get_config),
):
    filename, suffix = _filename_parts(filename)
    uploads = config.data_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    target = uploads / f"{identifier('book')}.{suffix}"
    await _save_upload(request, target, config.max_upload_bytes)
    try:
        return _create_uploaded_book(
            DocumentService(db), user["user_id"], filename, suffix, target,
            title=title, author=author, language=language,
        )
    except Exception:
        target.unlink(missing_ok=True)
        raise


@router.post("/books/batch")
async def upload_books_batch(
    files: list[UploadFile] = File(...),
    user=Depends(current_user), db=Depends(get_db), config=Depends(get_config),
):
    if len(files) > config.max_batch_files:
        raise HTTPException(413, f"批量上传最多支持 {config.max_batch_files} 个文件")

    uploads = config.data_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    service = DocumentService(db)
    items = []
    total_size = 0
    for upload in files:
        original_name = (upload.filename or "").replace("\\", "/").split("/")[-1].strip()
        item = {"filename": original_name, "book": None, "error": None}
        target = None
        try:
            filename, suffix = _filename_parts(upload.filename)
            target = uploads / f"{identifier('book')}.{suffix}"
            size, error = await _save_multipart_upload(
                upload, target, file_limit=config.max_upload_bytes,
                total_before=total_size, total_limit=config.max_batch_upload_bytes,
            )
            if error:
                item["error"] = error
            else:
                total_size += size
                item["book"] = _create_uploaded_book(
                    service, user["user_id"], filename, suffix, target,
                )
        except HTTPException as exc:
            item["error"] = str(exc.detail)
            if target:
                target.unlink(missing_ok=True)
        except Exception as exc:
            item["error"] = str(exc) or "文件上传失败"
            if target:
                target.unlink(missing_ok=True)
        finally:
            await upload.close()
        items.append(item)

    succeeded = sum(1 for item in items if item["book"] is not None)
    return {"items": items, "succeeded": succeeded, "failed": len(items) - succeeded}


@router.get("/books/{book_id}")
def document(book_id: str, user=Depends(current_user), db=Depends(get_db)):
    return DocumentService(db).get_owned(user["user_id"], book_id)


@router.get("/books/{book_id}/source")
def download_source(book_id: str, user=Depends(current_user), db=Depends(get_db), config=Depends(get_config)):
    service = DocumentService(db)
    book = service.owned_record(user["user_id"], book_id)
    target = service.resolve_source(book, config.data_dir / "uploads")
    return FileResponse(target, filename=book["file_name"], media_type="application/octet-stream")


@router.delete("/books/{book_id}")
def delete_book(book_id: str, user=Depends(current_user), db=Depends(get_db), config=Depends(get_config)):
    service = DocumentService(db)
    book = service.delete(user["user_id"], book_id)
    target = Path(book["source_path"]).resolve()
    uploads = (config.data_dir / "uploads").resolve()
    if uploads in target.parents:
        target.unlink(missing_ok=True)
    return {"ok": True}


@router.get("/books/{book_id}/chapters")
def chapters(book_id: str, user=Depends(current_user), db=Depends(get_db)):
    return DocumentService(db).chapters(user["user_id"], book_id)


@router.get("/books/{book_id}/chapters/{chapter_id}")
def chapter(book_id: str, chapter_id: str, user=Depends(current_user), db=Depends(get_db)):
    return DocumentService(db).chapter(user["user_id"], book_id, chapter_id)


@router.post("/books/{book_id}/parse", status_code=202)
def parse(book_id: str, background: BackgroundTasks, user=Depends(current_user), db=Depends(get_db)):
    service = DocumentService(db)
    book, task_id = service.start_parse(user["user_id"], book_id)
    background.add_task(service.run_extraction, book, task_id, "parse")
    return {"task_id": task_id, "status": "pending"}


@router.post("/extract", status_code=202)
def extract(payload: ExtractRequest, background: BackgroundTasks, user=Depends(current_user), db=Depends(get_db)):
    service = DocumentService(db)
    book, task_id, settings = service.start_extract(
        user["user_id"], payload.book_id, request=payload.model_dump(exclude={"book_id"}),
    )
    background.add_task(service.run_extraction, book, task_id, "extract", settings, payload.max_chapters)
    return {"task_id": task_id, "status": "pending"}


@router.get("/chapter-extractions")
def extractions(book_id: str = Query(...), user=Depends(current_user), db=Depends(get_db)):
    return DocumentService(db).extractions(user["user_id"], book_id)


@router.get("/summaries")
def summaries(book_id: str = Query(...), user=Depends(current_user), db=Depends(get_db)):
    return DocumentService(db).summaries(user["user_id"], book_id)


@router.post("/books/{book_id}/entity-resolutions")
def resolve_entity(book_id: str, payload: ResolutionRequest, user=Depends(current_user), db=Depends(get_db)):
    from .knowledge import resolve
    return resolve(db, user["user_id"], book_id, payload)


@router.post("/books/{book_id}/rebuild-knowledge")
def rebuild_knowledge(book_id: str, revision: int = Query(ge=0),
                      user=Depends(current_user), db=Depends(get_db)):
    from .knowledge import rebuild
    return rebuild(db, user["user_id"], book_id, revision)


@router.delete("/books/{book_id}/entity-resolutions/{resolution_id}")
def dismiss_resolution(book_id: str, resolution_id: str, revision: int = Query(ge=0),
                       user=Depends(current_user), db=Depends(get_db)):
    from .knowledge import dismiss_resolution as dismiss
    return dismiss(db, user["user_id"], book_id, resolution_id, revision)
