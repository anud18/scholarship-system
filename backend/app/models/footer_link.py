import enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import relationship

from app.db.base_class import Base

# Keeps the two payload shapes mutually exclusive even if a caller bypasses
# the pydantic layer. Declared on the model (not only in the migration) so a
# fresh DB built by Base.metadata.create_all() gets it too.
FOOTER_LINK_PAYLOAD_CHECK = (
    "(link_type = 'url' AND url IS NOT NULL AND object_name IS NULL) "
    "OR (link_type = 'file' AND object_name IS NOT NULL AND url IS NULL)"
)
FOOTER_LINK_PAYLOAD_CHECK_NAME = "ck_footer_links_payload_matches_type"


class FooterLinkType(enum.Enum):
    """How a footer link resolves for the visitor.

    ``url`` opens an external address in a new tab; ``file`` streams an
    admin-uploaded document (PDF/Office/ODF) through the backend proxy.
    """

    url = "url"
    file = "file"


class FooterLink(Base):
    """Admin-managed entry in the site footer's 相關連結 (Related Links) list.

    Exactly one of the two payload shapes is populated, keyed by ``link_type``:
    an external ``url``, or an uploaded document (``object_name`` + metadata).
    The pairing is enforced in the schema layer and by a DB CHECK constraint.
    """

    __tablename__ = "footer_links"
    __table_args__ = (CheckConstraint(FOOTER_LINK_PAYLOAD_CHECK, name=FOOTER_LINK_PAYLOAD_CHECK_NAME),)

    id = Column(Integer, primary_key=True, index=True)
    title_zh = Column(String(200), nullable=False)
    # Optional English label; the footer falls back to title_zh when unset.
    title_en = Column(String(200), nullable=True)
    link_type = Column(
        Enum(FooterLinkType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=FooterLinkType.url,
    )

    # link_type == url
    url = Column(String(1000), nullable=True)

    # link_type == file
    object_name = Column(String(500), nullable=True)
    original_filename = Column(String(500), nullable=True)
    content_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)

    sort_order = Column(Integer, nullable=False, default=0, index=True)
    # Lets an admin hide a link from the footer without losing its file.
    is_active = Column(Boolean, nullable=False, default=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    created_by_user = relationship("User", foreign_keys=[created_by])
