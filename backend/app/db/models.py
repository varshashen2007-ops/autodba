from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    orders: Mapped[List["Order"]] = relationship(
        "Order",
        back_populates="customer",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Customer(id={self.id}, "
            f"name='{self.name}', "
            f"email='{self.email}')>"
        )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    stock: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    order_items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="product",
    )

    def __repr__(self) -> str:
        return (
            f"<Product(id={self.id}, "
            f"name='{self.name}', "
            f"category='{self.category}', "
            f"price={self.price})>"
        )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    customer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )

    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
        index=True,
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
    )

    customer: Mapped["Customer"] = relationship(
        "Customer",
        back_populates="orders",
    )

    order_items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Order(id={self.id}, "
            f"customer_id={self.customer_id}, "
            f"total={self.total_amount}, "
            f"status='{self.status}')>"
        )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="order_items",
    )

    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="order_items",
    )

    def __repr__(self) -> str:
        return (
            f"<OrderItem(id={self.id}, "
            f"order_id={self.order_id}, "
            f"product_id={self.product_id}, "
            f"qty={self.quantity})>"
        )


class OptimizationMemoryModel(Base):
    __tablename__ = "optimization_memories"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    incident_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    query_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    query_text: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    diagnosis: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    recommendation: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    validation: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    benchmark: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    outcome: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    outcome_summary: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )

    embedding: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )