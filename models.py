from datetime import date
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, func, Boolean
)
from sqlalchemy.orm import relationship
from database import Base


class Rental(Base):
    """Skuter ijarasi: mijoz + skuter + shartlar + video ariza."""
    __tablename__ = "rentals"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, nullable=True, unique=True, index=True)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    passport = Column(String, nullable=True)          # Pasport seriyasi
    scooter_info = Column(String, nullable=False)     # Model + raqam
    daily_rate = Column(Float, nullable=False)        # Kunlik narx
    payment_type = Column(String, default="kunlik")   # kunlik / haftalik / oylik
    video_selfie = Column(String, nullable=True)      # Yuz + pasport video
    video_scooter = Column(String, nullable=True)     # Skuter holati video
    start_date = Column(Date, default=date.today)
    paid_until = Column(Date, default=date.today)
    status = Column(String, default="kutilmoqda", index=True)  # kutilmoqda / faol / tugagan
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    payments = relationship(
        "Payment", back_populates="rental",
        order_by="Payment.date.desc()",
        cascade="all, delete-orphan",
    )

    # ---------- Hisoblash ----------
    def debt_days(self) -> int:
        today = date.today()
        if not self.paid_until or self.paid_until >= today:
            return 0
        return (today - self.paid_until).days

    def debt_amount(self) -> float:
        return round(self.debt_days() * self.daily_rate, 2)

    def total_paid(self) -> float:
        return round(sum(p.amount for p in self.payments), 2)

    def paid_days(self) -> int:
        return int(sum(p.days_covered for p in self.payments))

    def days_left(self) -> int:
        """To'lov qancha kunga yetadi (qolgan kun)."""
        today = date.today()
        if not self.paid_until or self.paid_until < today:
            return 0
        return (self.paid_until - today).days

    def next_payment_date(self) -> date:
        """Keyingi to'lov sanasi = paid_until + 1 kun (yoki bugun)."""
        today = date.today()
        if not self.paid_until or self.paid_until < today:
            return today
        return self.paid_until


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    rental_id = Column(Integer, ForeignKey("rentals.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    days_covered = Column(Float, nullable=False)
    method = Column(String, default="naqd")     # naqd / karta / click / payme
    note = Column(String, nullable=True)
    confirmed = Column(Boolean, default=True)
    date = Column(DateTime, server_default=func.now())

    rental = relationship("Rental", back_populates="payments")
