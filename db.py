import aiosqlite
import config
import logging
import random
from aiogram import types


_db = None


class User:
    fields = 'user_id, vis_id, name, video_id, can_contact, is_blocked'

    def __init__(self, row):
        self.user_id = row[0]
        self.vis_id = row[1]
        self.name = row[2]
        self.video_id = row[3]
        self.can_contact = row[4] == 1
        self.can_contact_entered = row[4] is not None
        self.is_blocked = row[5] == 1


async def get_db():
    global _db
    if _db is not None and _db._running:
        return _db
    _db = await aiosqlite.connect(config.DATABASE)
    _db.row_factory = aiosqlite.Row
    exists_query = ("select count(*) from sqlite_master where type = 'table' "
                    "and name in ('intros', 'intro_search')")
    async with _db.execute(exists_query) as cursor:
        has_tables = (await cursor.fetchone())[0] == 2
    if not has_tables:
        logging.info('Creating tables')
        q = '''\
        create table intros (
            user_id integer primary key,
            vis_id integer not null,
            name text not null,
            video_id text,
            can_contact integer,
            is_blocked integer default 0,
            added_on timestamp not null default current_timestamp
        )'''
        await _db.execute(q)
        q = '''\
        create virtual table intro_search using fts3(name, tokenize=unicode61);
        '''
        await _db.execute(q)
        await _db.commit()
    return _db


async def on_shutdown(dp):
    if _db is not None and _db._running:
        await _db.close()


async def find_user(user: types.User) -> User:
    db = await get_db()
    cursor = await db.execute(
        f'select {User.fields} from intros where user_id = ?', (user.id,))
    row = await cursor.fetchone()
    return None if not row else User(row)


async def find_by_video(video_id: str) -> User:
    db = await get_db()
    cursor = await db.execute(
        f'select {User.fields} from intros where video_id = ?', (video_id,))
    row = await cursor.fetchone()
    return None if not row else User(row)


async def create_user(user: types.User, name: str):
    db = await get_db()
    # Generate vis_id
    while True:
        vis_id = random.randint(10000, 99999)
        cursor = await db.execute("select user_id from intros where vis_id = ?", (vis_id,))
        row = await cursor.fetchone()
        if not row:
            break
    # Insert values
    await db.execute(
        'insert into intros (user_id, vis_id, name) values (?, ?, ?)', (user.id, vis_id, name))
    await db.execute('insert into intro_search (docid, name) values (?, ?)', (user.id, name))
    await db.commit()


async def update_name(user: types.User, name: str):
    db = await get_db()
    await db.execute(
        'update intros set name = ? where user_id = ?', (name, user.id))
    await db.execute(
        'update intro_search set name = ? where docid = ?', (name, user.id))
    await db.commit()


async def delete_user(user: types.User):
    db = await get_db()
    await db.execute('delete from intros where user_id = ?', (user.id,))
    await db.commit()


async def random_user(user: types.User):
    db = await get_db()
    cursor = await db.execute(
        f'select {User.fields} from intros '
        'where user_id != ? and video_id is not null order by random() limit 1', (user.id,))
    row = await cursor.fetchone()
    return None if not row else User(row)


async def set_contact(user: types.User, value: bool):
    db = await get_db()
    await db.execute(
        'update intros set can_contact = ? where user_id = ?', (1 if value else 0, user.id))
    await db.commit()


async def set_video(user: types.User, video_id: str):
    db = await get_db()
    await db.execute(
        'update intros set video_id = ? where user_id = ?', (video_id, user.id))
    await db.commit()


async def find_by_name(keywords: str) -> list[User]:
    db = await get_db()
    cursor = await db.execute(
        f"select {User.fields} from intros "
        "where user_id in (select docid from intro_search where intro_search match ?) "
        "and is_blocked != 1 and video_id is not null",
        (keywords,))
    return [User(row) async for row in cursor]


async def block_user(user: types.User, value: bool = True):
    db = await get_db()
    await db.execute(
        'update intros set is_blocked = ? where user_id = ?', (1 if value else 0, user.id))
    await db.commit()
