# Shop Database — SQLAlchemy ORM

A command-line Python application for managing a shop database with users, products, and orders. Built with SQLAlchemy using modern 2.0+ syntax and includes a full integration test suite.

## Features

- **User management** — create and query users with email uniqueness constraints
- **Product catalog** — manage products with price validation (non-negative)
- **Order system** — link users to products with quantity tracking and shipped status
- **Data seeding** — idempotent seed function for demo data
- **Integration tests** — 5 automated test cases with pass/fail reporting
- **Formatted output** — clean table display in the terminal

## Tech Stack

- Python 3.9+ (uses `from __future__ import annotations`)
- SQLAlchemy 2.0+ (Mapped types, modern query syntax)
- SQLite

## Run Locally

```bash
git clone https://github.com/Pr1nc3B33/Flask-API-Code.git
cd Flask-API-Code

pip install -r requirements.txt

# Run the app
python dataBase.py

# Run integration tests
python dataBase.py --test
```

## Database Schema

| Table | Description |
|-------|-------------|
| User | id, name, email (unique), address |
| Product | id, name, price |
| Order | id, user_id (FK), product_id (FK), quantity, shipped |

## Operations

- Show all users, products, and orders
- Create new users, products, and orders
- Update product prices with validation
- View unshipped orders
- View order totals per user
- Delete users (cascades to orders)
