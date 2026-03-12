from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import ForeignKey, String, create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
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

    def __repr__(self) -> str:
        return f"<User(id={self.id}, name='{self.name}', email='{self.email}')>"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[int] = mapped_column(nullable=False)
    orders: Mapped[list["Order"]] = relationship(back_populates="product")

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name='{self.name}', price=${self.price})>"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    shipped: Mapped[bool] = mapped_column(default=False, nullable=False)

    user: Mapped[User] = relationship(back_populates="orders")
    product: Mapped[Product] = relationship(back_populates="orders")

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, user_id={self.user_id}, product_id={self.product_id}, qty={self.quantity}, shipped={self.shipped})>"


def initialize_database() -> None:
    """Create the application tables and apply any legacy schema fixes.

    Returns:
        None.
    """
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
    if price < 0:
        raise ValueError(f"Product price must be non-negative, got {price}")
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
    if quantity < 0:
        raise ValueError(f"Order quantity must be non-negative, got {quantity}")
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
    """Populate the database with the starter users, products, and orders.

    Uses idempotent operations so multiple runs do not duplicate records.

    Returns:
        None. Prints an error message if the commit fails.
    """
    try:
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
    except IntegrityError as e:
        session.rollback()
        print(f"✗ Integrity error during seed: {e}")
    except OperationalError as e:
        session.rollback()
        print(f"✗ Database error during seed: {e}")
    except ValueError as e:
        session.rollback()
        print(f"✗ Validation error during seed: {e}")


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
    """Update a product's price with validation and error handling.
    
    Args:
        session: SQLAlchemy session for database operations.
        product_name: Name of the product to update.
        new_price: New price (must be non-negative).
    
    Returns:
        None. Prints status to console.
    """
    if new_price < 0:
        print(f"✗ Invalid price: {new_price}. Price must be non-negative.")
        return
    
    product = session.scalar(select(Product).where(Product.name == product_name))
    if product is None:
        print(f"Product '{product_name}' not found.")
        return

    previous_price = product.price
    try:
        product.price = new_price
        session.commit()
        print(f"\nPrice updated: {product.name} ${previous_price} -> ${product.price}")
    except IntegrityError as e:
        session.rollback()
        print(f"✗ Integrity error updating price: {e}")
    except OperationalError as e:
        session.rollback()
        print(f"✗ Database error updating price: {e}")


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
    """Delete a user and cascade their orders from the database.
    
    Args:
        session: SQLAlchemy session for database operations.
        user_id: The ID of the user to delete.
    
    Returns:
        None. Prints status to console.
    """
    user = session.get(User, user_id)
    if user is None:
        print(f"User with ID {user_id} not found.")
        return

    deleted_name = user.name
    try:
        session.delete(user)
        session.commit()
        print(f"\nUser deleted: {deleted_name} (ID {user_id})")
    except IntegrityError as e:
        session.rollback()
        print(f"✗ Integrity error deleting user: {e}")
    except OperationalError as e:
        session.rollback()
        print(f"✗ Database error deleting user: {e}")


def run_integration_tests() -> None:
    """Run integration tests against an isolated temporary database."""
    print("\n" + "=" * 60)
    print("Running Integration Tests")
    print("=" * 60)

    test_database_path = DATABASE_PATH.with_name("shop_test.db")
    if test_database_path.exists():
        test_database_path.unlink()

    test_engine = create_engine(f"sqlite:///{test_database_path}")
    test_session_local = sessionmaker(bind=test_engine, expire_on_commit=False)
    Base.metadata.create_all(test_engine)

    tests_passed = 0

    try:
        with test_session_local() as session:
            try:
                seed_data(session)
                user_count = len(session.scalars(select(User)).all())
                product_count = len(session.scalars(select(Product)).all())
                order_count = len(session.scalars(select(Order)).all())
                assert user_count >= 2 and product_count >= 3 and order_count >= 4
                print("\n[Test 1] Seed data... ✓ PASS")
                tests_passed += 1
            except Exception as error:
                print(f"\n[Test 1] Seed data... ✗ FAIL: {error}")

            try:
                update_product_price(session, "Laptop", 850)
                updated_product = session.scalar(select(Product).where(Product.name == "Laptop"))
                assert updated_product is not None and updated_product.price == 850
                print("[Test 2] Update product price... ✓ PASS")
                tests_passed += 1
            except Exception as error:
                print(f"[Test 2] Update product price... ✗ FAIL: {error}")

            try:
                try:
                    get_or_create_product(session, name="Invalid", price=-50)
                    print("[Test 3] Reject invalid inputs... ✗ FAIL")
                except ValueError:
                    alice = get_or_create_user(session, name="Validation User", email="validation@x.com")
                    valid_product = get_or_create_product(session, name="Validation Product", price=25)
                    session.flush()
                    try:
                        ensure_order(
                            session,
                            user=alice,
                            product=valid_product,
                            quantity=-1,
                            shipped=False,
                        )
                        print("[Test 3] Reject invalid inputs... ✗ FAIL")
                    except ValueError:
                        print("[Test 3] Reject invalid inputs... ✓ PASS")
                        tests_passed += 1
            except Exception as error:
                print(f"[Test 3] Reject invalid inputs... ✗ FAIL: {error}")

            try:
                orders = session.scalars(
                    select(Order).join(Order.user).where(User.email == "alice@example.com")
                ).all()
                assert len(orders) >= 2
                print("[Test 4] Query seeded orders... ✓ PASS")
                tests_passed += 1
            except Exception as error:
                print(f"[Test 4] Query seeded orders... ✗ FAIL: {error}")

            try:
                removable_user = get_or_create_user(
                    session,
                    name="Delete Test",
                    email="delete-test@x.com",
                )
                removable_product = get_or_create_product(
                    session,
                    name="Delete Test Product",
                    price=99,
                )
                session.flush()
                ensure_order(
                    session,
                    user=removable_user,
                    product=removable_product,
                    quantity=1,
                    shipped=False,
                )
                session.commit()
                removable_user_id = removable_user.id
                delete_user(session, removable_user_id)
                assert session.get(User, removable_user_id) is None
                print("[Test 5] Delete user with cascaded orders... ✓ PASS")
                tests_passed += 1
            except Exception as error:
                print(f"[Test 5] Delete user with cascaded orders... ✗ FAIL: {error}")
    finally:
        test_engine.dispose()
        if test_database_path.exists():
            test_database_path.unlink()

    print("\n" + "=" * 60)
    print(f"Test Results: {tests_passed}/5 passed")
    print("=" * 60 + "\n")


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
    if "--test" in sys.argv:
        run_integration_tests()
    else:
        main()