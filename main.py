# ==================== 插件元数据 ====================
__plugin_meta__ = {
    'name': '谐音梗挑战',
    'author': 'baiyifei61-cmd',
    'description': '谐音梗答题游戏，看图猜谐音梗',
    'version': '1.0.0',
    'github': 'https://github.com/baiyifei61-cmd/xyg-plugin',
}


"""
谐音梗挑战插件
功能：谐音梗答题游戏
"""

import json
import os
import sqlite3
import time
import random
import re

from core.plugin.decorators import handler

# ==================== 数据库配置 ====================

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
LEVELS_DB = os.path.join(DATA_DIR, "levels.db")
GAME_DB = os.path.join(DATA_DIR, "challenge.db")

def init_db():
    """初始化数据库"""
    # 游戏状态表
    os.makedirs(DATA_DIR, exist_ok=True)  
    conn = sqlite3.connect(GAME_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT,
            level_id INTEGER,
            answers TEXT,
            start_time INTEGER,
            time_limit INTEGER,
            is_active INTEGER DEFAULT 1,
            participants TEXT DEFAULT '[]'
        )
    """)
    cursor.execute("PRAGMA table_info(game_state)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'group_id' not in columns:
        cursor.execute("ALTER TABLE game_state ADD COLUMN group_id TEXT")
    if 'participants' not in columns:
        cursor.execute("ALTER TABLE game_state ADD COLUMN participants TEXT DEFAULT '[]'")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            user_openid TEXT PRIMARY KEY,
            correct_count INTEGER DEFAULT 0,
            updated_at INTEGER
        )
    """)
    cursor.execute("PRAGMA table_info(scores)")
    score_columns = [row[1] for row in cursor.fetchall()]
    for col in ('rob_count', 'robbed_count', 'fail_count'):
        if col not in score_columns:
            cursor.execute(f"ALTER TABLE scores ADD COLUMN {col} INTEGER DEFAULT 0")
    conn.commit()
    conn.close()

def get_random_level():
    """从levels.db获取随机题目"""
    try:
        conn = sqlite3.connect(LEVELS_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM levels ORDER BY RANDOM() LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None
    except Exception as e:
        print(f"获取题目失败: {e}")
        return None

def get_active_game(group_id):
    """获取当前群的活跃游戏"""
    try:
        conn = sqlite3.connect(GAME_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM game_state WHERE is_active = 1 AND group_id = ? ORDER BY id DESC LIMIT 1",
            (group_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None
    except:
        return None

def save_game_state(group_id, level, answers):
    """保存游戏状态（按群独立）"""
    try:
        conn = sqlite3.connect(GAME_DB)
        cursor = conn.cursor()
        cursor.execute("UPDATE game_state SET is_active = 0 WHERE group_id = ?", (group_id,))
        answers_json = json.dumps(answers, ensure_ascii=False)
        cursor.execute(
            "INSERT INTO game_state (group_id, level_id, answers, start_time, time_limit, is_active) VALUES (?, ?, ?, ?, ?, 1)",
            (group_id, level['id'], answers_json, int(time.time()), 100)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"保存游戏失败: {e}")

def close_game(group_id):
    """关闭当前群的游戏"""
    try:
        conn = sqlite3.connect(GAME_DB)
        cursor = conn.cursor()
        cursor.execute("UPDATE game_state SET is_active = 0 WHERE group_id = ?", (group_id,))
        conn.commit()
        conn.close()
    except:
        pass

def add_correct_count(user_openid):
    """增加答对次数"""
    try:
        conn = sqlite3.connect(GAME_DB)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE scores SET correct_count = correct_count + 1, updated_at = ? WHERE user_openid = ?",
            (int(time.time()), user_openid)
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO scores (user_openid, correct_count, updated_at) VALUES (?, 1, ?)",
                (user_openid, int(time.time()))
            )
        conn.commit()
        conn.close()
    except:
        pass

def add_stat(user_openid, field, amount=1):
    """增加用户统计字段 (rob_count/robbed_count/fail_count)"""
    if field not in ('rob_count', 'robbed_count', 'fail_count'):
        return
    try:
        conn = sqlite3.connect(GAME_DB)
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE scores SET {field} = {field} + ?, updated_at = ? WHERE user_openid = ?",
            (amount, int(time.time()), user_openid)
        )
        if cursor.rowcount == 0:
            cursor.execute(
                f"INSERT INTO scores (user_openid, correct_count, {field}, updated_at) VALUES (?, 0, ?, ?)",
                (user_openid, amount, int(time.time()))
            )
        conn.commit()
        conn.close()
    except:
        pass

def get_user_stats(user_openid):
    """获取用户完整战绩"""
    try:
        conn = sqlite3.connect(GAME_DB)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT correct_count, rob_count, robbed_count, fail_count FROM scores WHERE user_openid = ?",
            (user_openid,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                'correct_count': row[0] or 0,
                'rob_count': row[1] or 0,
                'robbed_count': row[2] or 0,
                'fail_count': row[3] or 0,
            }
        return {'correct_count': 0, 'rob_count': 0, 'robbed_count': 0, 'fail_count': 0}
    except:
        return {'correct_count': 0, 'rob_count': 0, 'robbed_count': 0, 'fail_count': 0}

def add_participant(game_id, user_openid):
    """记录本轮参与抢答的用户"""
    try:
        conn = sqlite3.connect(GAME_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT participants FROM game_state WHERE id = ?", (game_id,))
        row = cursor.fetchone()
        participants = json.loads(row[0]) if row and row[0] else []
        if user_openid not in participants:
            participants.append(user_openid)
            cursor.execute(
                "UPDATE game_state SET participants = ? WHERE id = ?",
                (json.dumps(participants), game_id)
            )
            conn.commit()
        conn.close()
    except:
        pass

def get_participants(game_id):
    """获取本轮参与抢答的用户列表"""
    try:
        conn = sqlite3.connect(GAME_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT participants FROM game_state WHERE id = ?", (game_id,))
        row = cursor.fetchone()
        conn.close()
        return json.loads(row[0]) if row and row[0] else []
    except:
        return []

def _get_bot(event):
    """获取当前事件对应的 BotInstance"""
    from core.application import get_app

    app = get_app()
    return app.get_bot(event.appid) if app else None

def _mask_name(name):
    """昵称脱敏：只显示第一个字和两个*"""
    return f"{name[0]}**" if name else "匿名用户"

async def get_display_name(event, user_openid):
    """获取用户显示昵称：state=1 显示全部昵称，否则脱敏"""
    try:
        bot = _get_bot(event)
        if bot:
            row = await bot.log_service.db_fetch_one(
                "SELECT name, state FROM users WHERE user_id = ?", (user_openid,)
            )
            if row:
                name = row.get('name') or ''
                state = row.get('state') or 0
                if name:
                    return name if state == 1 else _mask_name(name)
    except Exception as e:
        print(f"获取昵称失败: {e}")
    return _mask_name('')

def get_user_correct_count(user_openid):
    """获取用户答对次数"""
    try:
        conn = sqlite3.connect(GAME_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT correct_count FROM scores WHERE user_openid = ?", (user_openid,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0
    except:
        return 0

def get_ranking(limit=10):
    """获取排行榜"""
    try:
        conn = sqlite3.connect(GAME_DB)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_openid, correct_count FROM scores ORDER BY correct_count DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"user_openid": r[0], "correct_count": r[1]} for r in rows]
    except:
        return []

def get_level_by_id(level_id):
    """根据ID获取题目"""
    try:
        conn = sqlite3.connect(LEVELS_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM levels WHERE id = ?", (level_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None
    except:
        return None

def get_answers(level):
    """获取答案列表"""
    answers = []
    if level.get('punned_phrase'):
        answers.append(level['punned_phrase'])
    if level.get('original_phrase'):
        answers.append(level['original_phrase'])
    return list(set(answers))

def generate_placeholders(text):
    """生成下划线占位"""
    return " ".join(["_" for _ in text])

# 初始化数据库
init_db()

# ==================== 指令处理器 ====================

@handler(r'^/? ?谐音梗挑战', name='谐音梗挑战', desc='开始谐音梗挑战')
async def start_challenge(event, match):
    """开始谐音梗挑战"""
    level = get_random_level()
    if not level:
        await event.reply("❌ 暂无题目，请稍后再试")
        return
    
    answers = get_answers(level)
    answer_text = answers[0] if answers else ""
    
    # 保存游戏状态
    save_game_state(event.chat_id, level, answers)
    
    # 构建题目消息
    md = "🎯 挑战谐音梗\n\n"
    if level.get('url1'):
        md += f"![{level.get('pun_word', '图片')} #200px #114px]({level['url1']})\n"
    md += f"这是 **{level.get('pun_word', '?')}**\n"
    if level.get('url2'):
        md += f"![{level.get('punned_phrase', '图片')} #200px #114px]({level['url2']})\n"
    md += f"这是 {generate_placeholders(answer_text)}\n\n"
    
    category = level.get('category', '未知')
    md += f">提示：题面类型为 **{category}**\n"
    md += ">答题限时：**100秒**\n"
    
    buttons = [
        [
            {"text": "抢答", "data": "抢答 ", "type": 2},
            {"text": "查看答案", "data": "#查看答案", "type": 2},
        ]
    ]
    await event.reply(md, buttons=buttons)

@handler(r'^抢答\s+(.+)$', name='抢答', desc='抢答谐音梗')
async def rob_answer(event, match):
    """抢答"""
    user_answer = match.group(1).strip()
    user_id = event.user_id
    chat_id = event.chat_id
    
    # 获取当前群的活跃游戏
    game = get_active_game(chat_id)
    if not game:
        await event.reply("❌ 暂无题目，请先发送【谐音梗挑战】")
        return
    
    # 检查是否超时
    elapsed = int(time.time()) - game['start_time']
    if elapsed > game['time_limit']:
        close_game(chat_id)
        await event.reply("⏰ 答题时间已到！")
        return
    
    # 获取题目详情
    level = get_level_by_id(game['level_id'])
    if not level:
        await event.reply("❌ 题目数据异常")
        return
    
    answers = json.loads(game['answers'])
    
    # 检查答案是否正确
    is_correct = False
    clean_answer = re.sub(r'\s+', '', user_answer)
    for correct in answers:
        clean_correct = re.sub(r'\s+', '', correct)
        if clean_answer == clean_correct:
            is_correct = True
            break
    
    if is_correct:
        # 关闭当前题目
        close_game(chat_id)
        
        # 记录答对次数与抢答次数
        add_correct_count(user_id)
        add_stat(user_id, 'rob_count')
        
        # 本轮其他参与者记为被抢答
        for other in get_participants(game['id']):
            if other != user_id:
                add_stat(other, 'robbed_count')
        
        # 构建成功消息
        md = "![🎉 抢答成功 #500px #150px](https://download.nature.qq.com/SnsShare/qq/Image_1782052541886_94.jpg)\n\n"
        md += "##🎉 抢答成功！\n\n"
        md += f"> 答案是 **{' / '.join(answers)}**\n"
        md += f"> 泰强啦，仅耗时 **{elapsed}秒**，请收下我的夸夸！\n\n"
        
        buttons = [
            [
                {"text": "🎯 继续挑战", "data": "谐音梗挑战", "type": 2},
                {"text": "🏆 大神排行榜", "data": "谐音梗排行榜", "type": 2},
            ]
        ]
        await event.reply(md, buttons=buttons)
        
        # 自动发新题
        new_level = get_random_level()
        if new_level:
            new_answers = get_answers(new_level)
            new_answer_text = new_answers[0] if new_answers else ""
            save_game_state(chat_id, new_level, new_answers)
            
            new_md = "🎯 挑战谐音梗\n\n"
            if new_level.get('url1'):
                new_md += f"![{new_level.get('pun_word', '图片')} #200px #114px]({new_level['url1']})\n"
            new_md += f"这是 **{new_level.get('pun_word', '?')}**\n"
            if new_level.get('url2'):
                new_md += f"![{new_level.get('punned_phrase', '图片')} #200px #114px]({new_level['url2']})\n"
            new_md += f"这是 {generate_placeholders(new_answer_text)}\n"
            
            new_category = new_level.get('category', '未知')
            new_md += f">提示：题面类型为 **{new_category}**\n"
            new_md += ">答题限时：**100秒**\n"
            
            new_buttons = [
                [
                    {"text": "抢答", "data": "抢答 ", "type": 2},
                    {"text": "查看答案", "data": "#查看答案", "type": 2},
                ]
            ]
            await event.reply(new_md, buttons=new_buttons)
    else:
        # 答错：记录失败次数与本轮参与
        add_stat(user_id, 'fail_count')
        add_participant(game['id'], user_id)
        remaining = game['time_limit'] - elapsed
        
        err_md = "🎯 挑战谐音梗\n\n"
        if level.get('url1'):
            err_md += f"![{level.get('pun_word', '图片')} #200px #114px]({level['url1']})\n\n"
        err_md += f"这是 **{level.get('pun_word', '?')}**\n\n"
        if level.get('url2'):
            err_md += f"![{level.get('punned_phrase', '图片')} #200px #114px]({level['url2']})\n\n"
        
        answer_text = answers[0] if answers else ""
        err_md += f"这是 {generate_placeholders(answer_text)}\n\n"
        err_md += "❌ 答案不对，再猜猜看！\n\n"
        category = level.get('category', '未知')
        err_md += f">提示：题面类型为 **{category}**\n"
        err_md += f">当前剩余时间：**{remaining}秒**\n\n"
        
        err_buttons = [
            [
                {"text": "继续抢答", "data": "抢答 ", "type": 2},
                {"text": "查看答案", "data": "#查看答案", "type": 2},
            ]
        ]
        await event.reply(err_md, buttons=err_buttons)

@handler(r'^#查看答案$', name='查看答案', desc='查看谐音梗答案')
async def view_answer(event, match):
    """查看答案"""
    chat_id = event.chat_id
    game = get_active_game(chat_id)
    if not game:
        await event.reply("❌ 暂无题目")
        return
    
    answers = json.loads(game['answers'])
    answers_text = " / ".join(answers)
    
    # 关闭当前题目
    close_game(chat_id)
    
    md = "![📖 答案揭晓 #500px #200px](https://download.nature.qq.com/SnsShare/61616/Image_1782052581781_517.jpg)\n\n"
    md += "## 📖 答案揭晓\n\n"
    md += f"> 公布谐音梗答案：\n"
    md += f"> **{answers_text}**\n\n"
    md += "> 本轮抢答结束，自动发起下一轮\n"
    
    await event.reply(md)
    
    # 自动发新题
    new_level = get_random_level()
    if new_level:
        new_answers = get_answers(new_level)
        new_answer_text = new_answers[0] if new_answers else ""
        save_game_state(chat_id, new_level, new_answers)
        
        new_md = "🎯 挑战谐音梗\n\n"
        if new_level.get('url1'):
            new_md += f"![{new_level.get('pun_word', '图片')} #200px #114px]({new_level['url1']})\n"
        new_md += f"这是 **{new_level.get('pun_word', '?')}**\n"
        if new_level.get('url2'):
            new_md += f"![{new_level.get('punned_phrase', '图片')} #200px #114px]({new_level['url2']})\n"
        new_md += f"这是 {generate_placeholders(new_answer_text)}\n"
        
        new_category = new_level.get('category', '未知')
        new_md += f">提示：题面类型为 **{new_category}**\n"
        new_md += ">答题限时：**100秒**\n"
        
        new_buttons = [
            [
                {"text": "抢答", "data": "抢答 ", "type": 2},
                {"text": "查看答案", "data": "#查看答案", "type": 2},
            ]
        ]
        await event.reply(new_md, buttons=new_buttons)

@handler(r'^谐音梗排行榜$', name='谐音梗排行榜', desc='谐音梗排行榜')
async def ranking(event, match):
    """排行榜"""
    ranking_list = get_ranking(10)
    
    md = "🏆 **谐音梗大神排行榜**\n\n"
    if not ranking_list:
        md += "暂无数据，快来挑战吧！\n\n"
    else:
        md += "👑 榜单TOP10\n"
        md += "━━━━━━━━━━━\n\n"
        
        medals = ['🥇', '🥈', '🥉']
        for idx, item in enumerate(ranking_list):
            medal = medals[idx] if idx < 3 else f"{idx + 1}."
            md += f"{medal} <@{item['user_openid']}> —— **{item['correct_count']}题**\n"
    
    md += "\n发送 **谐音梗挑战** 开始游戏！"
    await event.reply(md)

@handler(r'^我的战绩$', name='我的战绩', desc='查询我的战绩')
async def my_score(event, match):
    """我的战绩"""
    user_id = event.user_id
    stats = get_user_stats(user_id)
    name = await get_display_name(event, user_id)
    md = f"📊 **{name}** 的游玩战绩\n\n"
    md += f"> ✅ 累计答对：**{stats['correct_count']}题**\n"
    md += f"> ⚡ 抢答次数：**{stats['rob_count']}次**\n"
    md += f"> 💨 被抢答次数：**{stats['robbed_count']}次**\n"
    md += f"> ❌ 失败次数：**{stats['fail_count']}次**\n\n"
    md += "继续加油，冲击排行榜！"
    await event.reply(md)

@handler(r'^(我的)?游玩次数$', name='游玩次数', desc='查询我的游玩次数')
async def my_play_stats(event, match):
    """游玩次数"""
    await my_score(event, match)

@handler(r'^抢答$', name='抢答指令', desc='抢答指令')
async def rob_command(event, match):
    """纯抢答指令"""
    chat_id = event.chat_id
    game = get_active_game(chat_id)
    if not game:
        await event.reply("❌ 暂无题目，请先发送【谐音梗挑战】")
        return
    
    elapsed = int(time.time()) - game['start_time']
    if elapsed > game['time_limit']:
        close_game(chat_id)
        await event.reply("⏰ 答题时间已到！")
        return
    
    await event.reply("🏃 请输入：**抢答 你的答案**")

@handler(r'^结束挑战$', name='结束挑战', desc='结束当前挑战')
async def end_challenge(event, match):
    """结束当前题目"""
    chat_id = event.chat_id
    game = get_active_game(chat_id)
    if game:
        close_game(chat_id)
        await event.reply("✅ 当前题目已结束")
        return
    await event.reply("❌ 当前没有活跃的题目")