import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app.main import app, init_db

init_db()
application = app

if __name__ == '__main__':
    application.run()
