from flask import Flask, render_template, request, jsonify
from data_loader import DataLoader, JEWEL_TYPES

app = Flask(__name__)
loader = DataLoader()


@app.route('/')
def index():
    jewel_type_list = [
        {'id': jid, 'name': jinfo['name'],
         'seed_min': jinfo['seed_min'], 'seed_max': jinfo['seed_max'],
         'seed_step': jinfo['seed_step']}
        for jid, jinfo in JEWEL_TYPES.items()
    ]
    return render_template('index.html', jewel_types=jewel_type_list)


@app.route('/api/search', methods=['POST'])
def search():
    data = request.get_json()
    jewel_type = int(data.get('jewel_type', 0))
    seed = int(data.get('seed', 0))
    result = loader.find_duplicate_notables(jewel_type, seed)
    return jsonify(result)


@app.route('/api/parse_item', methods=['POST'])
def parse_item():
    data = request.get_json()
    item_text = data.get('item_text', '')
    result = loader.parse_item_text(item_text)
    return jsonify(result)


@app.route('/api/jewel_types')
def jewel_types():
    return jsonify([
        {'id': jid, 'name': jinfo['name'],
         'seed_min': jinfo['seed_min'], 'seed_max': jinfo['seed_max'],
         'seed_step': jinfo['seed_step']}
        for jid, jinfo in JEWEL_TYPES.items()
    ])


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
