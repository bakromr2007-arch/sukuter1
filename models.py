from datetime import date

from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from database import Base


class Rental(Base):
    """Bitta skuter ijarasi (mijoz + skuter + shartlar)."""
    __tablename__ = "rentals"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, nullable=True, unique=True, index=True)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    scooter_info = Column(String, nullable=False)
    daily_rate = Column(Float, nullable=False)
    video_file_id = Column(String, nullable=True)
    start_date = Column(Date, default=date.today)
    paid_until = Column(Date, default=date.today)
    status = Column(String, default="kutilmoqda")  # kutilmoqda / faol / tugagan
    created_at = Column(DateTime, server_default=func.now())

    payments = relationship(
        "Payment", back_populates="rental", order_by="Payment.date.desc()"
    )

    def debt_days(self) -> int:
        today = date.today()
        if self.paid_until >= today:
            return 0
        return (today - self.paid_until).days

    def debt_amount(self) -> float:
        return self.debt_days() * self.daily_rate

    def total_paid(self) -> float:
        return sum(p.amount for p in self.payments)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    rental_id = Column(Integer, ForeignKey("rentals.id"), nullable=False)
    amount = Column(Float, nullable=False)
    days_covered = Column(Float, nullable=False)
    date = Column(DateTime, server_default=func.now())

    rental = relationship("Rental", back_populates="payments")
