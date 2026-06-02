from app import create_app, db
from app.seed import seed_demo_data

app = create_app()

@app.cli.command("init-db")
def init_db():
    with app.app_context():
        db.create_all()
        print("Database initialized.")

@app.cli.command("seed")
def seed():
    with app.app_context():
        db.create_all()
        seed_demo_data()
        print("Seed data inserted.")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5000)
