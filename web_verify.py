
import os
import time
import sqlite3
import random
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder="templates")
DB_PATH = os.environ.get("DB_PATH", "/data/bot_database.db")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "realupilootbot")


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            balance REAL DEFAULT 0,
            total_earned REAL DEFAULT 0,
            total_withdrawn REAL DEFAULT 0,
            referral_count INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT 0,
            upi_id TEXT DEFAULT '',
            banned INTEGER DEFAULT 0,
            joined_at TEXT DEFAULT '',
            last_daily TEXT DEFAULT '',
            is_premium INTEGER DEFAULT 0,
            referral_paid INTEGER DEFAULT 0,
            ip_address TEXT DEFAULT '',
            ip_verified INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS verify_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ip TEXT,
            result TEXT,
            reason TEXT,
            user_agent TEXT,
            ts REAL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            game_name TEXT,
            bet_amount REAL DEFAULT 0,
            payout_amount REAL DEFAULT 0,
            result TEXT DEFAULT '',
            created_at TEXT DEFAULT ''
        )
    """)
    for k, v in {
        'ip_verification_enabled': 'true',
        'games_enabled': 'true',
        'mine_enabled': 'true',
        'mine_win_rate': '0.35',
        'mine_min_bet': '1',
        'mine_max_bet': '50',
        'mine_cooldown': '15',
        'mine_reward_multiplier': '2.0',
    }.items():
        cur.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", (k, v))
    for col, typ in [("ip_address","TEXT DEFAULT ''"),("ip_verified","INTEGER DEFAULT 0")]:
        try:
            cur.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def get_setting(key, default=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return default
    return row['value']


def is_enabled(key, default=True):
    value = get_setting(key, 'true' if default else 'false')
    return str(value).strip().lower() in ('1','true','yes','on','enabled')


def get_real_ip():
    for header in ("CF-Connecting-IP", "X-Real-IP", "X-Forwarded-For"):
        value = request.headers.get(header, "")
        if value:
            return value.split(",")[0].strip()
    return request.remote_addr or ""


def verify_user(user_id, ip):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cur.fetchone()
    if not user:
        conn.close()
        return False, {"message": "User not found.", "code": "ERR_USER_404"}
    if not is_enabled('ip_verification_enabled', True):
        cur.execute("UPDATE users SET ip_verified=1 WHERE user_id=?", (user_id,))
        conn.commit(); conn.close()
        return True, {"message": "IP verification is disabled by admin.", "status": "skipped", "user_id": user_id}
    cur.execute("UPDATE users SET ip_address=?, ip_verified=1 WHERE user_id=?", (ip, user_id))
    cur.execute("INSERT INTO verify_log (user_id, ip, result, reason, user_agent, ts) VALUES (?,?,?,?,?,?)", (user_id, ip, 'success', 'verified', request.headers.get('User-Agent',''), time.time()))
    conn.commit(); conn.close()
    return True, {"message": "Verification successful.", "status": "verified", "user_id": user_id}


@app.route('/')
def home():
    return jsonify({'status': 'running', 'service': 'web_verify'})


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': int(time.time())})


@app.route('/ip-verify')
def ip_verify():
    uid = request.args.get('uid', '').strip()
    if not uid.isdigit():
        return render_template('verify.html', page_state='error', title='Verification Failed', message='Invalid user ID.', error_code='ERR_INVALID_UID', user_id='—', session_hash='—', verified_at='—', device_type='—', bot_username=BOT_USERNAME), 400
    ok, data = verify_user(int(uid), get_real_ip())
    if not ok:
        return render_template('verify.html', page_state='error', title='Verification Failed', message=data['message'], error_code=data['code'], user_id=uid, session_hash='—', verified_at='—', device_type='—', bot_username=BOT_USERNAME), 400
    return render_template('verify.html', page_state='success', title='Verified Successfully', message=data['message'], error_code='—', user_id=uid, session_hash='—', verified_at='—', device_type='—', bot_username=BOT_USERNAME)


@app.route('/mine')
def mine_page():
    if not is_enabled('games_enabled', True) or not is_enabled('mine_enabled', True):
        return 'Mine game is disabled by admin.', 403
    uid = request.args.get('uid', '').strip()
    if not uid.isdigit():
        return 'Missing user id', 400
    return render_template('mine.html', user_id=int(uid), min_bet=float(get_setting('mine_min_bet', 1) or 1), max_bet=float(get_setting('mine_max_bet', 50) or 50), cooldown=int(float(get_setting('mine_cooldown', 15) or 15)), win_rate=float(get_setting('mine_win_rate', 0.35) or 0.35))


@app.route('/api/mine/play', methods=['POST'])
def mine_play():
    if not is_enabled('games_enabled', True) or not is_enabled('mine_enabled', True):
        return jsonify({'ok': False, 'error': 'disabled'}), 403
    data = request.get_json(silent=True) or request.form
    uid = int(data.get('uid', 0) or 0)
    bet = float(data.get('bet', 0) or 0)
    if uid <= 0:
        return jsonify({'ok': False, 'error': 'invalid_user'}), 400
    min_bet = float(get_setting('mine_min_bet', 1) or 1)
    max_bet = float(get_setting('mine_max_bet', 50) or 50)
    multiplier = float(get_setting('mine_reward_multiplier', 2.0) or 2.0)
    win_rate = float(get_setting('mine_win_rate', 0.35) or 0.35)
    if bet < min_bet or bet > max_bet:
        return jsonify({'ok': False, 'error': f'bet_must_be_between_{min_bet}_and_{max_bet}'}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT balance FROM users WHERE user_id=?', (uid,))
    row = cur.fetchone()
    if not row:
        conn.close(); return jsonify({'ok': False, 'error': 'user_not_found'}), 404
    balance = float(row['balance'] or 0)
    if balance < bet:
        conn.close(); return jsonify({'ok': False, 'error': 'low_balance'}), 400
    win = random.random() < win_rate
    payout = round(bet * multiplier, 2) if win else 0.0
    new_balance = round(balance - bet + payout, 2)
    cur.execute('UPDATE users SET balance=?, total_earned=total_earned+? WHERE user_id=?', (new_balance, payout if win else 0.0, uid))
    cur.execute('INSERT INTO game_results (user_id, game_name, bet_amount, payout_amount, result, created_at) VALUES (?,?,?,?,?,datetime("now","localtime"))', (uid, 'mine', bet, payout, 'win' if win else 'lose'))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'result': 'win' if win else 'lose', 'payout': payout, 'balance': new_balance})


@app.route('/api/mine/history/<int:user_id>')
def mine_history(user_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT result, bet_amount, payout_amount, created_at FROM game_results WHERE user_id=? AND game_name='mine' ORDER BY id DESC LIMIT 20", (user_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({'ok': True, 'history': rows})


ensure_schema()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
