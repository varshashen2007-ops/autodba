from app.db.models import Customer, Product, Order, OrderItem


def test_models_metadata():
    assert Customer.__tablename__ == "customers"
    assert Product.__tablename__ == "products"
    assert Order.__tablename__ == "orders"
    assert OrderItem.__tablename__ == "order_items"


def test_models_representation():
    c = Customer(id=1, name="Alice", email="alice@example.com")
    assert "Customer(id=1" in repr(c)

    p = Product(id=2, name="Keyboard", category="Electronics", price=49.99)
    assert "Product(id=2" in repr(p)

    o = Order(id=3, customer_id=1, total_amount=49.99, status="completed")
    assert "Order(id=3" in repr(o)

    oi = OrderItem(id=4, order_id=3, product_id=2, quantity=1, unit_price=49.99)
    assert "OrderItem(id=4" in repr(oi)
