from aiogram import Router

from . import admin, booking, catalog, my, reviews, start

_root: Router | None = None


def setup_routers() -> Router:
    """Корневой роутер (создаётся один раз: роутер aiogram нельзя подключить к двум диспетчерам)."""
    global _root
    if _root is None:
        _root = Router(name="root")
        # админский роутер первым: его фильтр IsAdmin пропускает только ADMIN_IDS
        _root.include_routers(admin.router, start.router, booking.router, catalog.router, my.router, reviews.router)
    _root._parent_router = None
    return _root
