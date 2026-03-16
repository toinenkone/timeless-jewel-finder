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


@app.route('/timeless/api/passives')
@requires_auth
def passives():
    return jsonify(loader.get_all_replacement_notables())


@app.route('/timeless/api/passives/<int:jewel_type>')
@requires_auth
def passives_for_jewel(jewel_type):
    return jsonify(loader.get_replacement_notables_for_jewel(jewel_type))


@app.route('/timeless/api/additions/<int:jewel_type>')
@requires_auth
def additions_for_jewel(jewel_type):
    return jsonify(loader.get_additions_for_jewel(jewel_type))


@app.route('/timeless/api/sockets')
@requires_auth
def sockets():
    return jsonify(loader.get_all_sockets())


@app.route('/timeless/api/socket_nodes/<int:socket_id>')
@requires_auth
def socket_nodes(socket_id):
    return jsonify(loader.get_socket_notable_nodes(socket_id))


@app.route('/timeless/api/search_notable', methods=['POST'])
@requires_auth
def search_notable():
    data = request.get_json()
    jewel_type = int(data.get('jewel_type', 0))
    notable_name = data.get('notable_name', '')
    min_count = max(2, min(5, int(data.get('min_count', 2))))
    result = loader.search_notable(jewel_type, notable_name, min_count)
    return jsonify(result)


@app.route('/timeless/api/search_conversion', methods=['POST'])
@requires_auth
def search_conversion():
    data = request.get_json()
    jewel_type = int(data.get('jewel_type', 0))
    socket_id = int(data.get('socket_id', 0))
    conversions = data.get('conversions', [])
    result = loader.search_conversion(jewel_type, socket_id, conversions)
    return jsonify(result)


@app.route('/timeless/api/search_notable_nodes', methods=['POST'])
@requires_auth
def search_notable_nodes():
    from data_loader import TIMELESS_JEWEL_ADDITIONS
    data = request.get_json()
    jewel_type = int(data.get('jewel_type', 0))
    node_ids = [int(n) for n in data.get('node_ids', [])]
    socket_id = data.get('socket_id')
    min_count = max(1, int(data.get('min_count', 1)))

    if 'target_global_id' in data:
        gid = int(data['target_global_id'])
    else:
        target_name = data.get('target_notable', '')
        gid = None
        for i, p in enumerate(loader.passives):
            if p['dn'] == target_name:
                gid = TIMELESS_JEWEL_ADDITIONS + i
                break
        if gid is None:
            return jsonify({"error": f"Notable '{target_name}' not found"})

    result = loader.search_notable_in_nodes(jewel_type, node_ids, gid, min_count, socket_id=socket_id)
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=3122)
