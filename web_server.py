import os
import logging
import sqlite3
import json
from datetime import datetime
from flask import request, jsonify, render_template
from anticheat import create_verification_app

# ================== CONFIG ==================

PORT = int(os.environ.get("PORT", 8000))
DB_PATH = os.environ.get("DB_PATH", "/data/bot_database.db")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "NeturalPredictorbot")

# ================== LOGGING ==================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logging.info("🚀 Starting IP Verification Server...")
logging.info(f"📂 DB_PATH: {DB_PATH}")
logging.info(f"🤖 BOT_USERNAME: {BOT_USERNAME}")

# ================== CREATE APP ==================

app = create_verification_app(
    DB_PATH=DB_PATH,
    BOT_USERNAME=BOT_USERNAME
)

# ================== EXTRA ROUTES ==================

@app.route("/debug")
def debug_info():
    return {
        "status": "running",
        "db_path": DB_PATH,
        "bot": BOT_USERNAME,
        "env_vars": list(os.environ.keys())
    }

@app.route("/ping")
def ping():
    return "pong"

# ================== ERROR HANDLING ==================

@app.errorhandler(404)
def not_found(e):
    return {
        "error": "Not Found",
        "message": "Invalid route"
    }, 404

@app.errorhandler(500)
def server_error(e):
    return {
        "error": "Server Error",
        "message": "Something went wrong"
    }, 500

# ================== START ==================

if __name__ == "__main__":
    logging.info(f"🌐 Running on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)


def _db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def _get_setting(cur, key, default=None):
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return row[0]

@app.route('/mine')
def mine_page():
    uid = request.args.get('uid', '0')
    return render_template('mine.html', uid=uid, bot_username=BOT_USERNAME)

@app.route('/api/mine/play', methods=['POST'])
def api_mine_play():
    data = request.get_json(silent=True) or {}
    user_id = int(data.get('user_id') or 0)
    bet = round(float(data.get('bet') or 0), 2)
    if user_id <= 0:
        return jsonify({'ok': False, 'message': 'Invalid user_id'}), 400
    conn = _db(); cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE user_id=?', (user_id,))
    user = cur.fetchone()
    if not user:
        conn.close(); return jsonify({'ok': False, 'message': 'User not found'}), 404
    min_bet = float(_get_setting(cur, 'mines_min_bet', 1) or 1)
    max_bet = float(_get_setting(cur, 'mines_max_bet', 50) or 50)
    if bet < min_bet or bet > max_bet:
        conn.close(); return jsonify({'ok': False, 'message': f'Bet must be between {min_bet} and {max_bet}'}), 400
    if float(user['balance'] or 0) < bet:
        conn.close(); return jsonify({'ok': False, 'message': 'Insufficient balance'}), 400
    force = str(_get_setting(cur, 'mines_force_result', 'auto') or 'auto').lower()
    win_ratio = int(_get_setting(cur, 'mines_win_ratio', 35) or 35)
    import random
    won = True if force == 'win' else False if force == 'lose' else random.randint(1, 100) <= win_ratio
    reward_mult = float(_get_setting(cur, 'mines_reward_multiplier', 1.8) or 1.8)
    reward = round(bet * reward_mult, 2) if won else 0.0
    max_round = float(_get_setting(cur, 'mines_max_winnings_per_round', reward or 100) or (reward or 100))
    reward = min(reward, max_round) if won else 0.0
    new_balance = round(float(user['balance'] or 0) - bet + reward, 2)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur.execute('UPDATE users SET balance=?, last_active_at=? WHERE user_id=?', (new_balance, now, user_id))
    cur.execute('INSERT INTO game_history (user_id, game_key, bet_amount, reward_amount, outcome, round_meta, created_at) VALUES (?,?,?,?,?,?,?)', (user_id, 'mines', bet, reward, 'win' if won else 'lose', json.dumps({'source': 'web'}), now))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'won': won, 'bet': bet, 'reward': reward, 'new_balance': new_balance})

@app.route('/api/mine/history/<int:user_id>')
def api_mine_history(user_id):
    conn = _db(); cur = conn.cursor()
    cur.execute('SELECT game_key, bet_amount, reward_amount, outcome, created_at FROM game_history WHERE user_id=? ORDER BY id DESC LIMIT 20', (user_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({'ok': True, 'items': rows})
