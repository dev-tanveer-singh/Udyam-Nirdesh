from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from ..deps import DB, EntrepreneurUser
from ..models import Application, Scheme
from ..schemas import ApplicationIn, ApplicationOut, ApplicationUpdate

router = APIRouter(prefix="/applications", tags=["applications"])


def _out(a: Application) -> ApplicationOut:
    return ApplicationOut(
        id=a.id, scheme_id=a.scheme_id, scheme_name=a.scheme.name,
        application_reference=a.application_reference, status=a.status,
        created_at=a.created_at, updated_at=a.updated_at,
    )


def _own(db, user_id: str, application_id: str) -> Application:
    app = db.scalar(
        select(Application).options(joinedload(Application.scheme))
        .where(Application.id == application_id, Application.user_id == user_id)
    )
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return app


@router.get("", response_model=list[ApplicationOut])
def list_applications(user: EntrepreneurUser, db: DB):
    rows = db.scalars(
        select(Application).options(joinedload(Application.scheme))
        .where(Application.user_id == user.id).order_by(Application.created_at, Application.id)
    ).all()
    return [_out(a) for a in rows]


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(body: ApplicationIn, user: EntrepreneurUser, db: DB):
    if db.get(Scheme, body.scheme_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown scheme_id")
    app = Application(
        user_id=user.id, scheme_id=body.scheme_id,
        application_reference=body.application_reference, status="documents_pending",
    )
    db.add(app)
    db.commit()
    return _out(_own(db, user.id, app.id))


@router.patch("/{application_id}", response_model=ApplicationOut)
def update_application(application_id: str, body: ApplicationUpdate, user: EntrepreneurUser, db: DB):
    app = _own(db, user.id, application_id)
    sent = body.model_fields_set
    if "status" in sent:
        if body.status is None:
            raise HTTPException(422, "status cannot be null")
        app.status = body.status
    if "application_reference" in sent:
        app.application_reference = body.application_reference
    db.commit()
    return _out(app)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(application_id: str, user: EntrepreneurUser, db: DB):
    app = _own(db, user.id, application_id)
    db.delete(app)
    db.commit()
