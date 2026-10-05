import asyncio
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, Teacher, get_owned_test
from app.core.config import get_settings
from app.models import GenerationJob, Material, Question, StudentAnswer, Test
from app.models.enums import JobStatus, MaterialStatus, QuestionStatus
from app.schemas.test import (
    GenerateTestRequest, GenerationJobOut, GoogleFormOut, QuestionOut, TestCreate, TestDetail, TestOut,
    TestUpdate,
)
from app.services.export.documents import (
    ExportOption, ExportQuestion, ExportTest, build_docx, build_pdf,
)
from app.services.export.google_forms import GoogleFormsError, create_google_form
from app.services.generation.service import run_generation_job
from app.services.llm.factory import exhausted_message

router = APIRouter(tags=["tests"])


@router.post("/tests", response_model=TestOut, status_code=status.HTTP_201_CREATED)
async def create_test(data: TestCreate, db: DbSession, user: Teacher) -> Test:
    materials = list(await db.scalars(
        select(Material).where(Material.id.in_(data.material_ids), Material.owner_id == user.id)
    ))
    if len(materials) != len(set(data.material_ids)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Частину матеріалів не знайдено")

    test = Test(
        owner_id=user.id,
        title=data.title,
        description=data.description,
        default_time_limit_sec=data.default_time_limit_sec,
    )
    test.materials = materials
    db.add(test)
    await db.commit()
    await db.refresh(test)
    return await get_owned_test(db, test.id, user)


@router.get("/tests", response_model=list[TestOut])
async def list_tests(db: DbSession, user: Teacher) -> list[Test]:
    rows = await db.scalars(
        select(Test)
        .where(Test.owner_id == user.id)
        .options(selectinload(Test.materials))
        .order_by(Test.created_at.desc())
    )
    return list(rows)


async def _export_model(db, test: Test, include_ai_verified: bool) -> ExportTest:
    """Затверджені (і за бажанням перевірені ШІ) питання тесту для експорту."""
    statuses = [QuestionStatus.APPROVED] + ([QuestionStatus.AI_VERIFIED] if include_ai_verified else [])
    questions = list(await db.scalars(
        select(Question).where(Question.test_id == test.id, Question.status.in_(statuses))
        .order_by(Question.position, Question.id)
    ))
    if not questions:
        raise HTTPException(status.HTTP_409_CONFLICT, "У тесті немає питань для експорту — затвердьте хоча б одне")
    return ExportTest(
        title=test.title,
        description=test.description,
        subtitle=("Матеріали: " + ", ".join(m.title for m in test.materials)) if test.materials else None,
        questions=[
            ExportQuestion(
                type=q.type.value, text=q.text, explanation=q.explanation,
                options=[ExportOption(o.text, o.is_correct) for o in sorted(q.options, key=lambda o: o.position)],
            )
            for q in questions
        ],
    )


@router.post("/tests/{test_id}/google-form", response_model=GoogleFormOut)
async def export_google_form(
    test_id: int, db: DbSession, user: Teacher, include_ai_verified: bool = True,
) -> GoogleFormOut:
    test = await get_owned_test(db, test_id, user)
    doc = await _export_model(db, test, include_ai_verified)
    try:
        s = get_settings()
        form = await create_google_form(doc, user.email, s.GOOGLE_APPS_SCRIPT_URL, s.GOOGLE_APPS_SCRIPT_SECRET)
    except GoogleFormsError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    test.google_form_id = form.form_id
    test.google_form_url = form.edit_url
    await db.commit()
    return GoogleFormOut(edit_url=form.edit_url, respond_url=form.respond_url, shared=form.shared)


@router.get("/tests/{test_id}/export")
async def export_test(
    test_id: int, db: DbSession, user: Teacher,
    format: Literal["docx", "pdf"] = "docx",
    answers: bool = False,
    include_ai_verified: bool = True,
) -> Response:
    """Тест для друку: для студентів або з відповідями та ключем."""
    test = await get_owned_test(db, test_id, user)
    doc = await _export_model(db, test, include_ai_verified)
    build = build_pdf if format == "pdf" else build_docx
    data = await asyncio.to_thread(build, doc, answers)

    suffix = "z_vidpovidyamy" if answers else "dlya_studentiv"
    ascii_name = f"test_{test.id}_{suffix}.{format}"
    ua_name = f"{test.title[:80]} ({'з відповідями' if answers else 'для студентів'}).{format}"
    media = ("application/pdf" if format == "pdf"
             else "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    return Response(data, media_type=media, headers={
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(ua_name)}",
    })


@router.get("/tests/{test_id}", response_model=TestDetail)
async def get_test(test_id: int, db: DbSession, user: Teacher, include_archived: bool = False) -> TestDetail:
    test = await get_owned_test(db, test_id, user)
    query = select(Question).where(Question.test_id == test.id)
    if not include_archived:
        query = query.where(Question.status != QuestionStatus.ARCHIVED)
    questions = await db.scalars(query.order_by(Question.position, Question.id))
    return TestDetail(
        **TestOut.model_validate(test).model_dump(),
        questions=[QuestionOut.model_validate(q) for q in questions],
    )


@router.patch("/tests/{test_id}", response_model=TestOut)
async def update_test(test_id: int, data: TestUpdate, db: DbSession, user: Teacher) -> Test:
    test = await get_owned_test(db, test_id, user)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(test, field, value)
    await db.commit()
    return test


@router.delete("/tests/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_test(test_id: int, db: DbSession, user: Teacher) -> None:
    test = await get_owned_test(db, test_id, user)
    # Тест із відповідями студентів видалити не можна (RESTRICT, історія потрібна для IRT)
    taken = await db.scalar(select(StudentAnswer.id).join(Question, Question.id == StudentAnswer.question_id)
                            .where(Question.test_id == test.id).limit(1))
    if taken is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Цей тест уже проходили студенти — видалити його не можна, бо результати потрібні "
            "для аналітики. Результати доступні в розділі «Результати».",
        )
    await db.delete(test)
    await db.commit()


# --- Генерація ---
@router.post(
    "/tests/{test_id}/generate",
    response_model=GenerationJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_generation(
    test_id: int,
    data: GenerateTestRequest,
    background: BackgroundTasks,
    db: DbSession,
    user: Teacher,
) -> GenerationJob:
    test = await get_owned_test(db, test_id, user)

    if not any(m.status == MaterialStatus.INDEXED for m in test.materials):
        raise HTTPException(status.HTTP_409_CONFLICT, "Немає оброблених матеріалів — дочекайтеся статусу «Готово»")

    limit_msg = exhausted_message()
    if limit_msg:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, limit_msg)

    running = await db.scalar(
        select(GenerationJob.id).where(
            GenerationJob.test_id == test.id,
            GenerationJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
    )
    if running:
        raise HTTPException(status.HTTP_409_CONFLICT, {"message": "Генерація вже триває", "job_id": running})

    job = GenerationJob(
        test_id=test.id,
        created_by=user.id,
        status=JobStatus.PENDING,
        params={
            **data.model_dump(mode="json"),
            "num_questions": data.num_questions,
            "question_types": data.question_types(),
        },
        total=data.num_questions,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background.add_task(run_generation_job, job.id)
    return job


@router.get("/tests/{test_id}/jobs", response_model=list[GenerationJobOut])
async def list_jobs(test_id: int, db: DbSession, user: Teacher) -> list[GenerationJob]:
    test = await get_owned_test(db, test_id, user)
    rows = await db.scalars(
        select(GenerationJob).where(GenerationJob.test_id == test.id).order_by(GenerationJob.id.desc())
    )
    return list(rows)


@router.get("/generation-jobs/{job_id}", response_model=GenerationJobOut)
async def get_job(job_id: int, db: DbSession, user: Teacher) -> GenerationJob:
    job = await db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Задачу генерації не знайдено")
    await get_owned_test(db, job.test_id, user)  # перевірка прав
    return job
