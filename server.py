from flask import Flask, request, jsonify, send_from_directory
import json
import os
import uuid

app = Flask(__name__)
TASKS_FILE = 'tasks.json'
CATEGORIES_FILE = 'categories.json'
NOTES_FILE = 'notes.json'

# --- ファイル初期化 ---
def initialize_json_file(filename, default_content):
    if not os.path.exists(filename):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(default_content, f, indent=4, ensure_ascii=False)

initialize_json_file(TASKS_FILE, [])
initialize_json_file(CATEGORIES_FILE, [])
initialize_json_file(NOTES_FILE, [])

# --- データ操作関数 ---
def read_data(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_data(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- APIエンドポイント ---
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# --- カテゴリAPI ---
@app.route('/categories', methods=['GET'])
def get_categories():
    categories = read_data(CATEGORIES_FILE)
    return jsonify(categories)

@app.route('/categories', methods=['POST'])
def add_category():
    data = request.get_json()
    if not data or 'name' not in data or not data['name'].strip():
        return jsonify({'error': 'カテゴリ名が必要です'}), 400
    
    categories = read_data(CATEGORIES_FILE)
    
    # 重複チェック
    if any(c['name'] == data['name'].strip() for c in categories):
        return jsonify({'error': '同じ名前のカテゴリが既に存在します'}), 409

    new_category = {
        'id': str(uuid.uuid4()),
        'name': data['name'].strip()
    }
    categories.append(new_category)
    write_data(CATEGORIES_FILE, categories)
    return jsonify(new_category), 201

@app.route('/categories/<category_id>', methods=['DELETE'])
def delete_category(category_id):
    categories = read_data(CATEGORIES_FILE)
    tasks = read_data(TASKS_FILE)

    # カテゴリが使用中かチェック
    if any(task.get('categoryId') == category_id for task in tasks):
        return jsonify({'error': 'このカテゴリはタスクで使用されているため削除できません'}), 400

    updated_categories = [c for c in categories if c['id'] != category_id]
    if len(categories) == len(updated_categories):
        return jsonify({'error': 'カテゴリが見つかりません'}), 404
        
    write_data(CATEGORIES_FILE, updated_categories)
    return '', 204

# --- タスクAPI ---
@app.route('/tasks', methods=['GET'])
def get_tasks():
    tasks = read_data(TASKS_FILE)
    categories = read_data(CATEGORIES_FILE)
    category_map = {c['id']: c['name'] for c in categories}

    # order属性がないタスクに初期値を設定 (下位互換性のため)
    needs_update = False
    for i, task in enumerate(tasks):
        if 'order' not in task:
            task['order'] = i
            needs_update = True
    
    if needs_update:
        write_data(TASKS_FILE, tasks)

    # orderに基づいてソート
    tasks.sort(key=lambda x: x.get('order', 0))

    for task in tasks:
        task['categoryName'] = category_map.get(task.get('categoryId'), '未分類')
        
    return jsonify(tasks)

@app.route('/tasks', methods=['POST'])
def add_task():
    data = request.get_json()
    if not data or 'text' not in data or not data['text'].strip():
        return jsonify({'error': 'タスク内容が必要です'}), 400

    tasks = read_data(TASKS_FILE)
    # 新しいタスクのorder値を決定 (既存の最大値+1)
    new_order = max([task.get('order', 0) for task in tasks] + [0]) + 1

    new_task = {
        'id': str(uuid.uuid4()),
        'text': data['text'],
        'dueDate': data.get('dueDate', ''),
        'categoryId': data.get('categoryId'),
        'order': new_order,
        'completed': False # 新しいタスクは未完了
    }
    tasks.append(new_task)
    write_data(TASKS_FILE, tasks)
    
    categories = read_data(CATEGORIES_FILE)
    category_map = {c['id']: c['name'] for c in categories}
    new_task['categoryName'] = category_map.get(new_task.get('categoryId'), '未分類')

    return jsonify(new_task), 201

@app.route('/tasks/order', methods=['PUT'])
def update_task_order():
    """タスクの並び順とカテゴリを一括更新"""
    data = request.get_json()
    ordered_ids = data.get('ordered_ids')
    category_updates = data.get('category_updates', {})

    if not ordered_ids:
        return jsonify({'error': '並び順データが必要です'}), 400

    tasks = read_data(TASKS_FILE)
    task_map = {task['id']: task for task in tasks}

    updated_tasks = []
    for i, task_id in enumerate(ordered_ids):
        if task_id in task_map:
            task = task_map[task_id]
            task['order'] = i
            # カテゴリが変更された場合は更新
            if task_id in category_updates:
                task['categoryId'] = category_updates[task_id]
            updated_tasks.append(task)

    write_data(TASKS_FILE, updated_tasks)
    return '', 204

@app.route('/tasks/<task_id>', methods=['PUT'])
def update_task(task_id):
    """指定されたIDのタスクを更新する"""
    data = request.get_json()
    if not data or 'text' not in data or not data['text'].strip():
        return jsonify({'error': 'タスク内容が必要です'}), 400

    tasks = read_data(TASKS_FILE)
    task_found = False
    for task in tasks:
        if task['id'] == task_id:
            task['text'] = data['text'].strip()
            task['dueDate'] = data.get('dueDate', '')
            task['categoryId'] = data.get('categoryId')
            task['completed'] = data.get('completed', False) # completed状態を更新
            task_found = True
            break
    
    if not task_found:
        return jsonify({'error': 'タスクが見つかりません'}), 404

    write_data(TASKS_FILE, tasks)

    # 更新したタスクにカテゴリ名を付けて返す
    categories = read_data(CATEGORIES_FILE)
    category_map = {c['id']: c['name'] for c in categories}
    updated_task = next((t for t in tasks if t['id'] == task_id), None)
    updated_task['categoryName'] = category_map.get(updated_task.get('categoryId'), '未分類')

    return jsonify(updated_task), 200

@app.route('/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    tasks = read_data(TASKS_FILE)
    updated_tasks = [task for task in tasks if task['id'] != task_id]

    if len(tasks) == len(updated_tasks):
        return jsonify({'error': 'タスクが見つかりません'}), 404

    write_data(TASKS_FILE, updated_tasks)
    return '', 204

# --- ノートAPI ---
from datetime import datetime

@app.route('/tasks/<task_id>/notes', methods=['GET'])
def get_notes(task_id):
    notes = read_data(NOTES_FILE)
    task_notes = [note for note in notes if note['taskId'] == task_id]
    # タイムスタンプでソートして返す
    task_notes.sort(key=lambda x: x['timestamp'])
    return jsonify(task_notes)

@app.route('/tasks/<task_id>/notes', methods=['POST'])
def add_note(task_id):
    data = request.get_json()
    if not data or 'content' not in data or not data['content'].strip():
        return jsonify({'error': 'ノート内容が必要です'}), 400

    notes = read_data(NOTES_FILE)
    new_note = {
        'id': str(uuid.uuid4()),
        'taskId': task_id,
        'timestamp': datetime.now().isoformat(),
        'content': data['content'].strip()
    }
    notes.append(new_note)
    write_data(NOTES_FILE, notes)
    return jsonify(new_note), 201

if __name__ == '__main__':
    app.run(debug=True, port=5001)
