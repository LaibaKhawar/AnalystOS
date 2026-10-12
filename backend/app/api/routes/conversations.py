from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, owned_conversation, owned_source
from app.api.schemas import AnalysisOut, AskIn, ConversationIn, ConversationOut, MessageOut
from app.core.errors import ValidationFailed
from app.db.base import utcnow
from app.db.models import Analysis, Conversation, Message, User
from app.db.session import get_db
from app.workers.dispatch import enqueue_analysis

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    data_source_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[Conversation]:
    query = db.query(Conversation).filter(Conversation.user_id == user.id)
    if data_source_id:
        query = query.filter(Conversation.data_source_id == data_source_id)
    return query.order_by(Conversation.updated_at.desc()).limit(100).all()


@router.post("", response_model=ConversationOut, status_code=201)
def create_conversation(
    body: ConversationIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Conversation:
    source = owned_source(db, user, body.data_source_id)
    if source.status != "ready":
        raise ValidationFailed("This data source is not ready yet")
    conversation = Conversation(
        user_id=user.id, data_source_id=source.id, title=(body.title or f"Analysis of {source.name}")[:300], state={}
    )
    db.add(conversation)
    db.commit()
    return conversation


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Conversation:
    return owned_conversation(db, user, conversation_id)


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    db.delete(owned_conversation(db, user, conversation_id))
    db.commit()


@router.post("/{conversation_id}/reset-context", response_model=ConversationOut)
def reset_context(
    conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Conversation:
    conversation = owned_conversation(db, user, conversation_id)
    conversation.state = {"history": (conversation.state or {}).get("history", [])}
    db.commit()
    return conversation


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def messages(conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[Message]:
    return list(owned_conversation(db, user, conversation_id).messages)


@router.get("/{conversation_id}/analyses", response_model=list[AnalysisOut])
def analyses(conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[Analysis]:
    owned_conversation(db, user, conversation_id)
    return db.query(Analysis).filter(Analysis.conversation_id == conversation_id).order_by(Analysis.created_at).all()


@router.post("/{conversation_id}/ask", response_model=AnalysisOut, status_code=202)
def ask(
    conversation_id: str, body: AskIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Analysis:
    conversation = owned_conversation(db, user, conversation_id)
    running = (
        db.query(Analysis)
        .filter(Analysis.conversation_id == conversation.id, Analysis.status.in_(["queued", "running"]))
        .count()
    )
    if running:
        raise ValidationFailed("An analysis is already running in this conversation")
    analysis = Analysis(
        conversation_id=conversation.id,
        user_id=user.id,
        data_source_id=conversation.data_source_id,
        question=body.question.strip(),
        status="queued",
    )
    db.add(analysis)
    db.flush()
    db.add(Message(conversation_id=conversation.id, role="user", content=analysis.question, analysis_id=analysis.id))
    if not conversation.messages or conversation.title.startswith("Analysis of"):
        conversation.title = analysis.question[:120]
    conversation.updated_at = utcnow()
    db.commit()
    enqueue_analysis(analysis.id)
    return analysis
