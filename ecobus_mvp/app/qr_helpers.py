import io

import qrcode
from sqlalchemy import and_, select

from app.models import QrToken, TokenStatus
from app.utils import end_of_month, generate_token, now_local


def make_qr_png(content: str) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img = img.resize((600, 600))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_or_rotate_token(db, passenger_id, valid_to_override=None, keep_existing_if_active=True) -> str:
    now = now_local().replace(tzinfo=None)

    stmt = select(QrToken).where(
        and_(
            QrToken.passenger_id == passenger_id,
            QrToken.status == TokenStatus.ACTIVE,
        )
    )
    existing_tokens = db.execute(stmt).scalars().all()

    if keep_existing_if_active and existing_tokens:
        # Tomamos el más reciente
        existing_tokens = sorted(existing_tokens, key=lambda x: x.valid_to or now, reverse=True)
        current = existing_tokens[0]

        # Revocar duplicados extra si existieran
        for extra in existing_tokens[1:]:
            extra.status = TokenStatus.REVOKED
            db.add(extra)

        new_valid_to = valid_to_override.replace(tzinfo=None) if valid_to_override else current.valid_to
        if new_valid_to and (current.valid_to is None or current.valid_to < new_valid_to):
            current.valid_to = new_valid_to
            db.add(current)

        db.flush()
        return current.token

    # Si no hay token activo, crear uno nuevo
    token = generate_token()
    valid_from = now
    valid_to = valid_to_override.replace(tzinfo=None) if valid_to_override else end_of_month(now).replace(tzinfo=None)

    tnew = QrToken(
        passenger_id=passenger_id,
        token=token,
        status=TokenStatus.ACTIVE,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    db.add(tnew)
    db.flush()
    return token
