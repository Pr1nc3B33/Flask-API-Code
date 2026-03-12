from __future__ import annotations

from pathlib import Path

from sqlalchemy import ForeignKey, String, create_engine, func, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


DATABASE_PATH = Path(__file__).with_name("shop.db")
engine = create_engine(f"sqlite:///{DATABASE_PATH}")
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    orders: Mapped[list["Order"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[int] = mapped_column(nullable=False)
    orders: Mapped[list["Order"]] = relationship(back_populates="product")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    shipped: Mapped[bool] = mapped_column(default=False, nullable=False)

    user: Mapped[User] = relationship(back_populates="orders")
    product: Mapped[Product] = relationship(back_populates="orders")


def initialize_database() -> None:
    Base.metadata.create_all(engine)
    synchronize_legacy_schema()


def synchronize_legacy_schema() -> None:
    inspector = inspect(engine)
    if "orders" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("orders")}
    if "shipped" in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE orders ADD COLUMN shipped BOOLEAN NOT NULL DEFAULT 0")
        )


def get_or_create_user(session: Session, *, name: str, email: str) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(name=name, email=email)
        session.add(user)
        session.flush()
    return user


def get_or_create_product(session: Session, *, name: str, price: int) -> Product:
    product = session.scalar(select(Product).where(Product.name == name))
    if product is None:
        product = Product(name=name, price=price)
        session.add(product)
        session.flush()
    return product


def ensure_order(
    session: Session,
    *,
    user: User,
    product: Product,
    quantity: int,
    shipped: bool,
) -> None:
    existing_order = session.scalar(
        select(Order).where(
            Order.user_id == user.id,
            Order.product_id == product.id,
            Order.quantity == quantity,
            Order.shipped == shipped,
        )
    )
    if existing_order is None:
        session.add(
            Order(
                user=user,
                product=product,
                quantity=quantity,
                shipped=shipped,
            )
        )


def seed_data(session: Session) -> None:
    alice = get_or_create_user(session, name="Alice Smith", email="alice@example.com")
    bob = get_or_create_user(session, name="Bob Johnson", email="bob@example.com")

    laptop = get_or_create_product(session, name="Laptop", price=999)
    smartphone = get_or_create_product(session, name="Smartphone", price=499)
    headphones = get_or_create_product(session, name="Headphones", price=199)

    ensure_order(session, user=alice, product=laptop, quantity=1, shipped=False)
    ensure_order(session, user=alice, product=headphones, quantity=2, shipped=True)
    ensure_order(session, user=bob, product=smartphone, quantity=1, shipped=False)
    ensure_order(session, user=bob, product=headphones, quantity=1, shipped=False)
    session.commit()


def ensure_demo_user_for_deletion(session: Session) -> int:
    user = session.scalar(select(User).where(User.email == "remove-me@example.com"))
    if user is None:
        user = User(name="Removal Demo", email="remove-me@example.com")
        session.add(user)
        session.flush()
    return user.id


def print_section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def print_table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    if not rows:
        print("No records found.")
        return

    widths = [len(header) for header in headers]
    normalized_rows = [tuple(str(value) for value in row) for row in rows]

    for row in normalized_rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    header_line = "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    divider_line = "  ".join("-" * widths[index] for index in range(len(headers)))

    print(header_line)
    print(divider_line)
    for row in normalized_rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def show_users(session: Session) -> None:
    print_section("Users")
    rows = [
        (user.id, user.name, user.email)
        for user in session.scalars(select(User).order_by(User.name))
    ]
    print_table(("ID", "Name", "Email"), rows)


def show_products(session: Session) -> None:
    print_section("Products")
    rows = [
        (product.id, product.name, f"${product.price}")
        for product in session.scalars(select(Product).order_by(Product.name))
    ]
    print_table(("ID", "Product", "Price"), rows)


def show_orders(session: Session) -> None:
    print_section("Orders")
    statement = (
        select(Order.id, User.name, Product.name, Order.quantity, Order.shipped)
        .join(Order.user)
        .join(Order.product)
        .order_by(User.name, Product.name, Order.id)
    )

    rows = [
        (
            order_id,
            user_name,
            product_name,
            quantity,
            "Shipped" if shipped else "Pending",
        )
        for order_id, user_name, product_name, quantity, shipped in session.execute(statement)
    ]
    print_table(("ID", "User", "Product", "Qty", "Status"), rows)


def update_product_price(session: Session, product_name: str, new_price: int) -> None:
    product = session.scalar(select(Product).where(Product.name == product_name))
    if product is None:
        return

    previous_price = product.price
    product.price = new_price
    session.commit()
    print(f"\nPrice updated: {product.name} ${previous_price} -> ${product.price}")


def show_unshipped_orders(session: Session) -> None:
    print_section("Unshipped Orders")
    statement = (
        select(Order.id, User.name, Product.name, Order.quantity)
        .join(Order.user)
        .join(Order.product)
        .where(Order.shipped.is_(False))
        .order_by(User.name, Product.name, Order.id)
    )

    rows = list(session.execute(statement))
    print_table(("ID", "User", "Product", "Qty"), rows)


def show_order_totals(session: Session) -> None:
    print_section("Orders Per User")
    statement = (
        select(User.name, func.count(Order.id))
        .outerjoin(User.orders)
        .group_by(User.id, User.name)
        .order_by(User.name)
    )

    rows = list(session.execute(statement))
    print_table(("User", "Total Orders"), rows)


def delete_user(session: Session, user_id: int) -> None:
    user = session.get(User, user_id)
    if user is None:
        return

    deleted_name = user.name
    session.delete(user)
    session.commit()
    print(f"\nUser deleted: {deleted_name} (ID {user_id})")


def main() -> None:
    initialize_database()

    with SessionLocal() as session:
        seed_data(session)
        show_users(session)
        show_products(session)
        show_orders(session)
        update_product_price(session, "Laptop", 899)
        show_unshipped_orders(session)
        show_order_totals(session)
        delete_user(session, ensure_demo_user_for_deletion(session))


if __name__ == "__main__":
    main()