"""Точка входа: python -m app"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, MenuButtonWebApp, WebAppInfo
from aiohttp import web

from .config import load_config
from .covers import ensure_covers
from .db import DB
from .fsm_storage import SQLiteStorage
from .handlers import setup_routers
from .middlewares import UserMiddleware
from .notifications import scheduler_loop
from .media import set_upload_dir
from .ui import set_covers_dir
from .web.server import create_app

log = logging.getLogger("beauty")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    db = DB(cfg.db_path)
    await db.connect()
    covers_dir = cfg.data_dir / "covers"
    ensure_covers(covers_dir)
    set_covers_dir(covers_dir)
    set_upload_dir(cfg.data_dir / "uploads")

    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=SQLiteStorage(db), db=db, cfg=cfg)
    dp.message.outer_middleware(UserMiddleware())
    dp.callback_query.outer_middleware(UserMiddleware())
    dp.include_router(setup_routers())

    await bot.set_my_commands([BotCommand(command="start", description="🎀 Главное меню"),
                               BotCommand(command="menu", description="💅 Меню")])
    for aid in cfg.admin_ids:
        try:
            await bot.set_my_commands([BotCommand(command="start", description="🎀 Главное меню"),
                                       BotCommand(command="admin", description="👑 Админ-панель"),
                                       BotCommand(command="panel", description="🖥 Веб-админка")],
                                      scope=BotCommandScopeChat(chat_id=aid))
        except Exception as e:  # noqa: BLE001 — админ ещё не писал боту
            log.warning("admin %s commands: %s", aid, e)
    if cfg.webapp_url:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Запись ♡", web_app=WebAppInfo(url=cfg.webapp_url)))

    runner = None
    if cfg.run_web:
        runner = web.AppRunner(create_app(db, bot, cfg))
        await runner.setup()
        await web.TCPSite(runner, cfg.web_host, cfg.web_port).start()
        log.info("Mini App: http://%s:%s (публичный адрес: %s)", cfg.web_host, cfg.web_port, cfg.webapp_url or "не задан")

    sched = asyncio.create_task(scheduler_loop(bot, db, cfg))
    me = await bot.me()
    log.info("Бот @%s запущен. Админы: %s", me.username, ", ".join(map(str, cfg.admin_ids)) or "не заданы!")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        sched.cancel()
        if runner:
            await runner.cleanup()
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code not in (None, 0):
            raise
