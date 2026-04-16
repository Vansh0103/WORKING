from core import *


@bot.message_handler(commands=['getdb'])
def send_db(message):
    if is_admin(message.from_user.id):
        with open(DB_PATH, "rb") as f:
            bot.send_document(message.chat.id, f)
        log_admin_action(message.from_user.id, "getdb", "Downloaded database")
@bot.message_handler(func=lambda m: m.text == "🔙 User Panel" and is_admin(m.from_user.id))
def back_user_panel(message):
    safe_send(
        message.chat.id,
        f"{pe('check')} Switched to User Panel.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@bot.message_handler(commands=["start"])
def start_handler(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "User"
    chat_id = message.chat.id

    if get_setting("bot_maintenance") and not is_admin(user_id):
        safe_send(
            chat_id,
            f"{pe('gear')} <b>Bot Under Maintenance</b>\n\n"
            f"{pe('hourglass')} We'll be back soon!\n"
            f"{pe('info')} Contact: {HELP_USERNAME}"
        )
        return

    args = message.text.split()
    referred_by = 0
    if len(args) > 1:
        try:
            ref_id = int(args[1])
            if ref_id != user_id:
                referred_by = ref_id
        except:
            pass

    is_new = create_user(user_id, username, first_name, referred_by)
    update_user(user_id, username=username, first_name=first_name)

    if not check_force_join(user_id):
        send_join_message(chat_id)
        return

    send_welcome(chat_id, user_id, first_name, is_new)

    if is_new and not is_admin(user_id):
        try:
            total = get_user_count()
            safe_send(
                ADMIN_ID,
                f"{pe('bell')} <b>New User Joined!</b>\n\n"
                f"{pe('disguise')} <b>Name:</b> {first_name}\n"
                f"{pe('link')} <b>Username:</b> @{username}\n"
                f"{pe('info')} <b>ID:</b> <code>{user_id}</code>\n"
                f"{pe('chart_up')} <b>Total Users:</b> {total}\n"
                f"{pe('arrow')} <b>Referred by:</b> {referred_by or 'None'}"
            )
        except:
            pass

def send_welcome(chat_id, user_id, first_name, is_new=False):
    user = get_user(user_id)
    if not user:
        return
    balance = user["balance"]
    per_refer = get_setting("per_refer")
    min_withdraw = get_setting("min_withdraw")
    welcome_image = get_setting("welcome_image")
    try:
        bot_info = bot.get_me()
        bot_username = bot_info.username
    except:
        bot_username = "bot"
    refer_link = f"https://t.me/{bot_username}?start={user_id}"
    caption = (
        f"{pe('crown')} <b>Welcome to UPI Loot Pay!</b> {pe('fire')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{pe('smile')} Hello, <b>{first_name}</b>!\n\n"
        f"{pe('fly_money')} <b>Your Balance:</b> ₹{balance:.2f}\n"
        f"{pe('star')} <b>Per Refer:</b> ₹{per_refer}\n"
        f"{pe('down_arrow')} <b>Min Withdraw:</b> ₹{min_withdraw}\n\n"
        f"{pe('zap')} <b>How to Earn?</b>\n"
        f"  {pe('play')} Share your referral link\n"
        f"  {pe('play')} Friends complete verification → You earn ₹{per_refer}\n"
        f"  {pe('play')} Complete Tasks & earn more!\n"
        f"  {pe('play')} Withdraw to UPI instantly!\n\n"
        f"{pe('link')} <b>Your Refer Link:</b>\n"
        f"<code>{refer_link}</code>\n\n"
        f"{pe('sparkle')} <i>No limit! Earn unlimited!</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    try:
        bot.send_photo(chat_id, welcome_image, caption=caption, parse_mode="HTML", reply_markup=get_main_keyboard(user_id))
    except:
        safe_send(chat_id, caption, reply_markup=get_main_keyboard(user_id))

# ======================== VERIFY JOIN ========================
@bot.callback_query_handler(func=lambda call: call.data == "verify_join")
def verify_join(call):
    user_id = call.from_user.id

    if check_force_join(user_id):
        safe_answer(call, "✅ Channel verification complete!")

        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        user = get_user(user_id)

        if not user:
            create_user(
                user_id,
                call.from_user.username or "",
                call.from_user.first_name or "User"
            )
            user = get_user(user_id)

        if is_enabled("ip_verification_enabled", True) and int(user["ip_verified"] or 0) != 1:
            send_ip_verify_message(call.message.chat.id, user_id)
            return

        ok, reason = anticheat.can_pay_referral_bonus(user_id)

        if ok:
            process_referral_bonus(user_id)

        send_welcome(call.message.chat.id, user_id, call.from_user.first_name or "User", True)
    else:
        safe_answer(call, "❌ Please join ALL channels first!", True)


@bot.callback_query_handler(func=lambda call: call.data == "check_ip_verified")
def check_ip_verified(call):
    user_id = call.from_user.id
    user = get_user(user_id)

    if not user:
        safe_answer(call, "❌ User not found!", True)
        return

    if is_enabled("ip_verification_enabled", True) and int(user["ip_verified"] or 0) != 1:
        safe_answer(call, "❌ IP verification failed ", True)
        return

    ok, reason = anticheat.can_pay_referral_bonus(user_id)

    if ok:
        process_referral_bonus(user_id)
        safe_answer(call, "✅ IP verification complete!")
    else:
        safe_answer(call, f"❌ {reason}", True)
        return

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass

    send_welcome(call.message.chat.id, user_id, call.from_user.first_name or "User", False)
# ======================== BALANCE ========================
@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def balance_handler(message):
    user_id = message.from_user.id
    if not check_force_join(user_id):
        send_join_message(message.chat.id)
        return
    user = get_user(user_id)
    if not user:
        safe_send(message.chat.id, "Please send /start first.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🏧 Withdraw", callback_data="open_withdraw"),
        types.InlineKeyboardButton("👥 Refer & Earn", callback_data="open_refer"),
    )
    markup.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh_balance"))
    text = (
        f"{pe('money')} <b>Your Wallet</b> {pe('diamond')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{pe('fly_money')} <b>Balance:</b> ₹{user['balance']:.2f}\n"
        f"{pe('chart_up')} <b>Total Earned:</b> ₹{user['total_earned']:.2f}\n"
        f"{pe('check')} <b>Total Withdrawn:</b> ₹{user['total_withdrawn']:.2f}\n"
        f"{pe('thumbs_up')} <b>Total Referrals:</b> {user['referral_count']}\n\n"
        f"{pe('star')} <b>Per Refer:</b> ₹{get_setting('per_refer')}\n"
        f"{pe('down_arrow')} <b>Min Withdraw:</b> ₹{get_setting('min_withdraw')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    safe_send(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "refresh_balance")
def refresh_balance(call):
    user_id = call.from_user.id
    user = get_user(user_id)
    if not user:
        safe_answer(call, "Error!", True)
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🏧 Withdraw", callback_data="open_withdraw"),
        types.InlineKeyboardButton("👥 Refer & Earn", callback_data="open_refer"),
    )
    markup.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh_balance"))
    text = (
        f"{pe('money')} <b>Your Wallet</b> {pe('diamond')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{pe('fly_money')} <b>Balance:</b> ₹{user['balance']:.2f}\n"
        f"{pe('chart_up')} <b>Total Earned:</b> ₹{user['total_earned']:.2f}\n"
        f"{pe('check')} <b>Total Withdrawn:</b> ₹{user['total_withdrawn']:.2f}\n"
        f"{pe('thumbs_up')} <b>Total Referrals:</b> {user['referral_count']}\n\n"
        f"{pe('star')} <b>Per Refer:</b> ₹{get_setting('per_refer')}\n"
        f"{pe('down_arrow')} <b>Min Withdraw:</b> ₹{get_setting('min_withdraw')}\n\n"
        f"{pe('refresh')} <i>Just refreshed!</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    safe_edit(call.message.chat.id, call.message.message_id, text, reply_markup=markup)
    safe_answer(call, "✅ Refreshed!")

# ======================== REFER ========================
@bot.message_handler(func=lambda m: m.text == "👥 Refer")
def refer_handler(message):
    user_id = message.from_user.id
    if not check_force_join(user_id):
        send_join_message(message.chat.id)
        return
    user = get_user(user_id)
    if not user:
        safe_send(message.chat.id, "Please send /start first.")
        return
    show_refer(message.chat.id, user_id, user)

@bot.callback_query_handler(func=lambda call: call.data == "open_refer")
def open_refer_cb(call):
    user_id = call.from_user.id
    user = get_user(user_id)
    if not user:
        safe_answer(call, "Error!", True)
        return
    safe_answer(call)
    show_refer(call.message.chat.id, user_id, user)



def show_refer(chat_id, user_id, user):
    levels = get_referral_levels()
    try:
        bot_username = bot.get_me().username
    except:
        bot_username = "bot"
    refer_link = f"https://t.me/{bot_username}?start={user_id}"
    share_msg = f"Join using my link and help me unlock rewards: {refer_link}"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(
        "📤 Share My Referral Link",
        url=f"https://t.me/share/url?url={refer_link}&text={share_msg}"
    ))
    markup.add(types.InlineKeyboardButton("🏆 Referral Board", callback_data="ref_board"))
    levels_text = "\n".join([f"• {format_referral_level_line(x)}" for x in levels])
    text = (
        f"{pe('fire')} <b>Refer & Earn</b> {pe('fly_money')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{pe('link')} <b>Your Referral Link:</b>\n"
        f"<code>{refer_link}</code>\n\n"
        f"{pe('thumbs_up')} <b>Total Referrals:</b> {user['referral_count']}\n"
        f"{pe('money')} <b>Referral Earnings:</b> Included in wallet\n\n"
        f"{pe('star')} <b>3-Level Rewards</b>\n{levels_text}\n\n"
        f"{pe('info')} Direct referrals increase your total referrals and leaderboard rank.\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    safe_send(chat_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "ref_board")
def referral_board_cb(call):
    safe_answer(call)
    rows = get_top_referrers(10)
    if not rows:
        safe_send(call.message.chat.id, f"{pe('info')} No referrals yet.")
        return
    text = f"{pe('trophy')} <b>Top Referrers</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(rows, start=1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        name = row['first_name'] or row['username'] or str(row['user_id'])
        text += f"{medal} <b>{name}</b> — {int(row['referral_count'] or 0)} referrals\n"
    safe_send(call.message.chat.id, text)
