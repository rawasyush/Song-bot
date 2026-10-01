import asyncio
from collections import defaultdict
import secrets
import time
from aiogram import Router, Bot
from aiogram.types import (
    InlineQuery, InputMediaAudio, InlineQueryResultArticle, InputTextMessageContent,
    ChosenInlineResult, InlineQuery, FSInputFile, URLInputFile
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Music
from app.utils.bot_data import BotData
from app.keyboards.inline import Inlines
from app.config import config
from app.utils.helpers import HandlersHelper


router = Router()

last_query_time = defaultdict(float)
pending_tasks = {}
DEBOUNCE_TIME = 0.5


@router.inline_query()
async def inline_query_handler(query: InlineQuery, bot_data: BotData, db: AsyncSession):
    text = query.query.strip()
    user_id = query.from_user.id
    inlines = Inlines(bot_data.texts)

    if not text:
        return await query.answer(
            [InlineQueryResultArticle(
                id=secrets.token_hex(8),
                title=bot_data.texts.inline_query_empty,
                input_message_content=InputTextMessageContent(
                    message_text=bot_data.texts.inline_query_empty_send
                ),
                reply_markup=inlines.music_lyrics(None, only_switch=True)
            )],
            cache_time=0
        )
    
    current_time = time.time()
    last_query_time[user_id] = current_time

    if user_id in pending_tasks:
        pending_tasks[user_id].cancel()

    async def delayed_execution(expected_time):
        await asyncio.sleep(DEBOUNCE_TIME)
        if last_query_time[user_id] == expected_time:
            await HandlersHelper.process_query(query, bot_data, db)
        pending_tasks.pop(user_id, None)

    pending_tasks[user_id] = asyncio.create_task(delayed_execution(current_time))


@router.chosen_inline_result()
async def chosen_result_handler(result: ChosenInlineResult, bot: Bot, db: AsyncSession, bot_data: BotData):
    inline_message_id = result.inline_message_id
    if not inline_message_id:
        return
    
    parts = result.result_id.split(":")
    if len(parts) != 2:
        return
    
    song_id = parts[1]
    res = await db.execute(select(Music).filter(Music.id == song_id))
    song = res.scalar_one_or_none()
    
    if not song:
        return
    
    inlines = Inlines(bot_data.texts)
    caption = bot_data.texts.song_music_caption.replace("<song_id>", song.id)
    
    if song.file_id:
        file_id = song.file_id
        await bot.edit_message_media(
            inline_message_id=inline_message_id,
            media=InputMediaAudio(
                media=file_id,
                caption=caption
            ),
            reply_markup=inlines.music_lyrics(None, only_switch=True)
        )
        return
        
    await bot.edit_message_media(
        inline_message_id=inline_message_id,
        media=InputMediaAudio(
            media=config.LOADING_SONG,
            caption=bot_data.texts.song_loading
        ),
        reply_markup=inlines.music_lyrics(None, only_switch=True)
    )
    
    file_path = await HandlersHelper.music_download(song)
    
    # Because Aiogram dose not support input file for inline_message
    message = await bot.send_audio(
        result.from_user.id, 
        audio=FSInputFile(file_path),
        title=song.title,
        performer=', '.join([artist['name'] for artist in song.artists]),
        thumbnail=URLInputFile(song.photo)
    )
    await message.delete()
    
    await bot.edit_message_media(
        inline_message_id=inline_message_id,
        media=InputMediaAudio(
            media=message.audio.file_id, 
            caption=caption
        ),
        reply_markup=inlines.music_lyrics(None, only_switch=True)
    )
    
    song.file_id = message.audio.file_id
    await db.commit()
