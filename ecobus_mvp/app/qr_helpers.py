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


def create_or_rotate_token(db, passenger_id) -> str:
    # Revoke previous active token and create a new one for current month
    now = now_local()

    stmt = select(QrToken).where(
        and_(
            QrToken.passenger_id == passenger_id,
            QrToken.status == TokenStatus.ACTIVE,
        )
    )
    for t in db.execute(stmt).scalars().all():
        t.status = TokenStatus.REVOKED
        db.add(t)

    token = generate_token()
    valid_from = now
    valid_to = end_of_month(now)

    tnew = QrToken(
        passenger_id=passenger_id,
        token=token,
        status=TokenStatus.ACTIVE,
        valid_from=valid_from.replace(tzinfo=None),
        valid_to=valid_to.replace(tzinfo=None),
    )
    db.add(tnew)
    db.flush()
    return token
