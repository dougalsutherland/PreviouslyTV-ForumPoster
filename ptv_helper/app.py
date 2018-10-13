from __future__ import unicode_literals
import os
import warnings

from flask import Flask, g, request, url_for
from flask_bcrypt import Bcrypt
import peewee
from playhouse.db_url import connect
from raven.contrib.flask import Sentry


app = Flask(__name__)
app.config.from_object('ptv_helper.config.default')
if 'PTV_SETTINGS' in os.environ:
    app.config.from_envvar('PTV_SETTINGS')
elif os.path.exists(os.path.join(os.path.dirname(__file__), 'config/deploy.py')):
    app.config.from_object('ptv_helper.config.deploy')

for handler in app.config.get('LOG_HANDLERS', []):
    app.logger.addHandler(handler)

if 'SENTRY_DSN' in app.config:
    sentry = Sentry(app, dsn=app.config['SENTRY_DSN'])
else:
    warnings.warn("No SENTRY_DSN config; not setting up Sentry.")

bcrypt = Bcrypt(app)

db = connect(app.config['DATABASE'])


@app.before_request
def before_request():
    g.db = db
    try:
        g.db.connect()
    except peewee.OperationalError as e:
        if not str(e).startswith('Connection already open'):
            raise


@app.after_request
def after_request(response):
    g.db.close()
    return response


sentinel = object()


def get_next_url(nxt=sentinel):
    if nxt is sentinel:
        nxt = request.args.get('next')
    if nxt:
        return request.script_root + nxt
    return url_for('index')
