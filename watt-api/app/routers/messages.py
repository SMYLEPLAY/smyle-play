"""
Endpoints messagerie 1:1.

Routes (toutes auth requise) :
  GET  /messages/threads                  → mes conversations (tri last_message_at desc)
  POST /messages/threads/{user_id}        → ouvre ou récupère un thread avec un user
  GET  /messages/threads/{thread_id}      → messages d'un thread (50 derniers)
  POST /messages/threads/{thread_id}/send → envoie un message
  POST /messages/threads/{thread_id}/read → marque les messages du thread comme lus
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.message import Message, MessageThread
from app.models.notification import NotificationType
from app.models.trade import TradeOffer
from app.models.user import User
from app.schemas.message import MessageCreate, MessageRead, ThreadMessagesResponse, ThreadRead
from app.services.notifications import create_notification

router = APIRouter(prefix="/messages", tags=["messages"])

# S-03 sécurité (2026-09-02) — marqueur « proposition d'échange » posté par
# le client (ui/messaging/messaging.js) dans le fil : `__TRADE_OFFER__<uuid>`.
# Le front le rend sous forme de carte cliquable ; sans contrôle serveur,
# n'importe qui pouvait poster `__TRADE_OFFER__');alert(1)//` (XSS stocké
# chez l'interlocuteur). Règle : le suffixe DOIT être l'UUID d'une offre
# existante, envoyée par l'expéditeur du message au destinataire du fil ;
# le contenu stocké est la forme canonique (UUID normalisé).
_TRADE_MARK = "__TRADE_OFFER__"


async def _canonical_trade_marker(
    content: str, *, sender_id: UUID, receiver_id: UUID, db: AsyncSession
) -> str:
    """Valide un marqueur d'échange et renvoie sa forme canonique, sinon 400."""
    raw = content[len(_TRADE_MARK):].strip()
    try:
        offer_id = UUID(raw)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Marqueur d'échange invalide")
    offer = (await db.execute(
        select(TradeOffer).where(TradeOffer.id == offer_id)
    )).scalar_one_or_none()
    if (offer is None
            or offer.sender_id != sender_id
            or offer.receiver_id != receiver_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Marqueur d'échange invalide")
    return f"{_TRADE_MARK}{offer.id}"


def _canonical_pair(a: UUID, b: UUID) -> tuple[UUID, UUID]:
    """Retourne (min, max) pour garantir unicité de la paire en DB."""
    return (a, b) if str(a) < str(b) else (b, a)


async def _get_thread_or_404(
    thread_id: UUID, user_id: UUID, db: AsyncSession
) -> MessageThread:
    thread = (await db.execute(
        select(MessageThread).where(
            MessageThread.id == thread_id,
            or_(
                MessageThread.participant_a == user_id,
                MessageThread.participant_b == user_id,
            ),
        )
    )).scalar_one_or_none()
    if not thread:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Thread introuvable")
    return thread


@router.get("/threads", response_model=list[ThreadRead])
async def list_threads(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ThreadRead]:
    """Retourne tous les threads du user, triés par activité récente."""
    threads = (await db.execute(
        select(MessageThread)
        .where(
            or_(
                MessageThread.participant_a == current_user.id,
                MessageThread.participant_b == current_user.id,
            )
        )
        .order_by(MessageThread.last_message_at.desc().nullslast())
    )).scalars().all()

    result = []
    for t in threads:
        other_id = t.participant_b if t.participant_a == current_user.id else t.participant_a

        other = (await db.execute(
            select(User.artist_name, User.avatar_url).where(User.id == other_id)
        )).first()

        # Dernier message (preview)
        last_msg = (await db.execute(
            select(Message.content)
            .where(Message.thread_id == t.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        # Compteur unread (messages que l'autre a envoyés, non lus)
        unread = (await db.execute(
            select(func.count())
            .where(
                Message.thread_id == t.id,
                Message.sender_id != current_user.id,
                Message.read_at.is_(None),
            )
        )).scalar_one()

        result.append(ThreadRead(
            id=t.id,
            other_user_id=other_id,
            other_user_name=other.artist_name if other else None,
            other_user_avatar=other.avatar_url if other else None,
            last_message_at=t.last_message_at,
            last_message_preview=last_msg[:60] if last_msg else None,
            unread_count=unread,
            created_at=t.created_at,
        ))

    return result


@router.post("/threads/{user_id}", response_model=ThreadRead)
async def get_or_create_thread(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadRead:
    """Ouvre un thread avec un user (idempotent — retourne l'existant si déjà ouvert)."""
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Impossible de s'envoyer un message à soi-même")

    # Vérifier que l'autre user existe
    other = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not other:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")

    pa, pb = _canonical_pair(current_user.id, user_id)

    # Chercher thread existant
    thread = (await db.execute(
        select(MessageThread).where(
            MessageThread.participant_a == pa,
            MessageThread.participant_b == pb,
        )
    )).scalar_one_or_none()

    if not thread:
        thread = MessageThread(participant_a=pa, participant_b=pb)
        db.add(thread)
        await db.flush()
        await db.commit()
        await db.refresh(thread)

    return ThreadRead(
        id=thread.id,
        other_user_id=user_id,
        other_user_name=other.artist_name,
        other_user_avatar=other.avatar_url,
        last_message_at=thread.last_message_at,
        last_message_preview=None,
        unread_count=0,
        created_at=thread.created_at,
    )


@router.get("/threads/{thread_id}", response_model=ThreadMessagesResponse)
async def get_thread_messages(
    thread_id: UUID,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadMessagesResponse:
    """Retourne les 50 derniers messages du thread."""
    thread = await _get_thread_or_404(thread_id, current_user.id, db)
    other_id = (thread.participant_b
                if thread.participant_a == current_user.id
                else thread.participant_a)

    other = (await db.execute(
        select(User.artist_name).where(User.id == other_id)
    )).scalar_one_or_none()

    msgs = (await db.execute(
        select(Message)
        .where(Message.thread_id == thread_id)
        .order_by(Message.created_at.asc())
        .limit(min(limit, 100))
    )).scalars().all()

    return ThreadMessagesResponse(
        thread_id=thread_id,
        other_user_id=other_id,
        other_user_name=other,
        messages=[MessageRead.model_validate(m) for m in msgs],
    )


@router.post("/threads/{thread_id}/send", response_model=MessageRead,
             status_code=status.HTTP_201_CREATED)
async def send_message(
    thread_id: UUID,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageRead:
    """Envoie un message dans un thread existant."""
    thread = await _get_thread_or_404(thread_id, current_user.id, db)

    receiver_id = (thread.participant_b
                   if thread.participant_a == current_user.id
                   else thread.participant_a)

    content = payload.content.strip()
    if content.startswith(_TRADE_MARK):
        content = await _canonical_trade_marker(
            content, sender_id=current_user.id, receiver_id=receiver_id, db=db
        )

    msg = Message(
        thread_id=thread_id,
        sender_id=current_user.id,
        content=content,
    )
    db.add(msg)

    # Mettre à jour last_message_at sur le thread
    thread.last_message_at = datetime.now(timezone.utc)

    # Notif au destinataire (fire-and-forget)
    await create_notification(
        db,
        user_id=receiver_id,
        type=NotificationType.MESSAGE,
        actor_id=current_user.id,
        target_type="thread",
        target_id=thread_id,
        metadata={"preview": content[:80]},
    )

    await db.commit()
    await db.refresh(msg)
    return MessageRead.model_validate(msg)


@router.post("/threads/{thread_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_thread_read(
    thread_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Marque tous les messages non lus du thread (envoyés par l'autre) comme lus."""
    await _get_thread_or_404(thread_id, current_user.id, db)
    now = datetime.now(timezone.utc)
    await db.execute(
        update(Message)
        .where(
            Message.thread_id == thread_id,
            Message.sender_id != current_user.id,
            Message.read_at.is_(None),
        )
        .values(read_at=now)
    )
    await db.commit()
