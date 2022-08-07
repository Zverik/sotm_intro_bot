import config
import db
from aiogram import Bot, Dispatcher, executor, types
from aiogram.utils.callback_data import CallbackData

bot = Bot(config.API_TOKEN)
dp = Dispatcher(bot)
USER_CB = CallbackData('show_user', 'id')


@dp.message_handler(commands=['start'])
async def welcome(message: types.Message):
    user = await db.find_user(message.from_user)
    if user is not None:
        return await msg(message)
    await message.answer(
        'Hi! This bot helps State of the Map 2022 participants know each other.\n'
        'First, please write your full name.'
    )


async def present_user(user: db.User):
    if user.can_contact:
        caption = (f'This is {user.name}. If you want to say hi, reply to this message '
                   'and I will forward your reply to them. Or press /random for '
                   'another participant.')
    else:
        caption = f'{user.name}.\nPress /random for another participant.'
    bot.send_video(user.video_id, caption=caption)


@dp.message_handler(commands=['random'])
async def random(message: types.Message):
    user = await db.find_user(message.from_user)
    if user is not None:
        return await msg(message)
    rnd = await db.random_user(message.from_user)
    if not rnd:
        await message.answer('Sorry, could not find anyone')
        return
    await present_user(rnd)


@dp.message_handler(commands=['name'])
async def change_name(message: types.Message):
    await message.answer('Sorry, cannot change names yet.')


@dp.message_handler(commands=['contact'])
async def change_contact(message: types.Message):
    await message.reply(
        'Do you want other people contacting you (via this bot)?',
        reply_markup=make_yesno_keyboard())


@dp.message_handler(commands=['delete'])
async def delete_user_command(message: types.Message):
    kbd = types.InlineKeyboardMarkup(row_width=2)
    kbd.add(
        types.InlineKeyboardButton('Yes', callback_data='delete_me'),
        types.InlineKeyboardButton('No', callback_data='dont_delete'),
    )
    await message.answer('Delete your name and video from the database?', reply_markup=kbd)


@dp.callback_query_handler(text='delete_me')
@dp.callback_query_handler(text='dont_delete')
async def delete_answered(query: types.CallbackQuery):
    user = await db.find_user(query.from_user)
    if not user:
        await query.answer('This is weird. Please re-register.')
        return
    if query.data == 'delete_me':
        await db.delete_user(query.from_user)
        await query.answer('You were deleted.')
        return
    await bot.delete_message(query.from_user, query.message.message_id)


def make_yesno_keyboard():
    kbd = types.InlineKeyboardMarkup(row_width=2)
    kbd.add(
        types.InlineKeyboardButton('Yes', callback_data='contact_yes'),
        types.InlineKeyboardButton('No', callback_data='contact_no'),
    )
    return kbd


@dp.callback_query_handler(text='contact_yes')
@dp.callback_query_handler(text='contact_no')
async def set_contact_yes(query: types.CallbackQuery):
    user = await db.find_user(query.from_user)
    if not user:
        await query.answer('This is weird. Please re-register.')
        return
    await db.set_contact(query.from_user, query.data == 'contact_yes')
    if user.video_id is not None:
        await query.answer('Saved.')
        await send_invite()
        return
    await query.answer(
        'Great! Now please record a video 10-15 seconds in length.\n\n'
        'In it say hi, tell your name and where are you from, '
        'and what do you like to do in OpenStreetMap.'
    )


@dp.message_handler()
async def msg(message: types.Message):
    if message.from_user.is_bot:
        return
    if len(message.text.strip()) < 2:
        return

    user = await db.find_user(message.from_user)
    if not user:
        if len(message.text.strip().split()) >= 2:
            # There was no name but there is now
            await db.create_user(message.chat.id, message.text.strip())
            await message.reply(
                'Thank you! When you want to change it, type /name. '
                'Now, do you want other people contacting you (via this bot)?',
                reply_markup=make_yesno_keyboard())
            return
        await message.answer('Please write your full name.')
        return

    if not user.can_contact_entered:
        await message.reply(
            'Do you want other people contacting you (via this bot)?',
            reply_markup=make_yesno_keyboard())
        return

    if message.reply_to_message and message.reply_to_message.video:
        reply_user = await db.find_by_video(message.reply_to_message.video.file_id)
        if not reply_user:
            await message.answer('Sorry, could not find the user to forward your reply to.')
        elif not reply_user.can_contact:
            await message.answer('Sorry, the user asked not to contact them.')
        else:
            await message.forward(reply_user.user_id)
            await message.answer('Forwarded them your message.')
        return

    found = await db.find_by_name(message.text.strip())
    if not found:
        await message.reply('Sorry, could not find anyone with that name.')
    elif len(found) == 1:
        await present_user(found[0])
    else:
        kbd = types.InlineKeyboardMarkup(row_width=1)
        for fu in found:
            kbd.add(types.InlineKeyboardButton(fu.name, callback_data=USER_CB(id=fu.user_id)))
        await message.reply('Found multiple participants:', reply_markup=kbd)


async def send_invite(user: types.User):
    await bot.send_message(
        user.id,
        'Please enter a name to find a person, or tap on /random to get a random introduction.')


@dp.message_handler(content_types=types.ContentType.VIDEO)
async def update_video(message: types.Message):
    user = await db.find_user(message.from_user)
    if not user:
        return await msg(message)

    if message.video.duration < 7:
        await message.reply('Please record another one, around 10-15 seconds long.')
        return
    if message.video.duration > 20:
        await message.reply('Please record another one, at most 20 seconds long.')
        return

    await db.set_video(message.from_user, message.video.file_id)
    if not user.video_id:
        await message.answer(
            'Thank you for the video! Now people can find it and get aquainted with you.')
    else:
        await message.answer('Thank you for the new video!')
    await send_invite()


@dp.message_handler(content_types=types.ContentType.VIDEO_NOTE)
async def video_note(message: types.Message):
    await message.reply('Please send (or attach) a proper video, not a video note.')


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_shutdown=db.on_shutdown)