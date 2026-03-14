import os
from functools import wraps
from flask import Flask, render_template, request, jsonify, Response
from data_loader import DataLoader, JEWEL_TYPES

app = Flask(__name__)

AUTH_USERNAME = os.environ.get('AUTH_USERNAME', 'admin')
AUTH_PASSWORD = os.environ.get('AUTH_PASSWORD', 'changeme')

loader = DataLoader()


def _authenticate():
    return Response(
        'Authentication required.',
        401,
        {'WWW-Authenticate': 'Basic realm="Timeless Jewel Finder"'},
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != AUTH_USERNAME or auth.password != AUTH_PASSWORD:
            return _authenticate()
        return f(*args, **kwargs)
    return decorated


@app.route('/timeless/')
@requires_auth
def index():
    jewel_type_list = [
        {'id': jid, 'name': jinfo['name'],
         'seed_min': jinfo['seed_min'], 'seed_max': jinfo['seed_max'],
         'seed_step': jinfo['seed_step']}
        for jid, jinfo in JEWEL_TYPES.items()
    ]
    return render_template('index.html', jewel_types=jewel_type_list)


@app.route('/timeless/api/search', methods=['POST'])
@requires_auth
def search():
    data = request.get_json()
    jewel_type = int(data.get('jewel_type', 0))
    seed = int(data.get('seed', 0))
    result = loader.find_duplicate_notables(jewel_type, seed)
    return jsonify(result)


@app.route('/timeless/api/parse_item', methods=['POST'])
@requires_auth
def parse_item():
    data = request.get_json()
    item_text = data.get('item_text', '')
    result = loader.parse_item_text(item_text)
    return jsonify(result)


@app.route('/timeless/api/jewel_types')
@requires_auth
def jewel_types():
    return jsonify([
        {'id': jid, 'name': jinfo['name'],
         'seed_min': jinfo['seed_min'], 'seed_max': jinfo['seed_max'],
         'seed_step': jinfo['seed_step']}
        for jid, jinfo in JEWEL_TYPES.items()
    ])


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=3122)
