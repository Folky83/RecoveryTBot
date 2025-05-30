"""
Type safety helpers for the Mintos bot
"""
from typing import Optional, TypeGuard, Any, Dict, List
from telegram import Update, CallbackQuery, Message
from telegram.ext import Application


def is_valid_callback_query(query: Optional[CallbackQuery]) -> TypeGuard[CallbackQuery]:
    """Type guard to check if callback query is valid and has required attributes"""
    return query is not None and hasattr(query, 'data') and hasattr(query, 'message')


def is_valid_message(message: Optional[Message]) -> TypeGuard[Message]:
    """Type guard to check if message is valid"""
    return message is not None and hasattr(message, 'chat_id')


def is_valid_application(app: Optional[Application]) -> TypeGuard[Application]:
    """Type guard to check if application is valid"""
    return app is not None and hasattr(app, 'bot') and hasattr(app, 'updater')


def safe_get_chat_id(update: Update) -> Optional[int]:
    """Safely extract chat_id from update"""
    try:
        if update.effective_chat:
            return update.effective_chat.id
        if update.message and hasattr(update.message, 'chat_id'):
            return update.message.chat_id
        if update.callback_query and update.callback_query.message:
            msg = update.callback_query.message
            if hasattr(msg, 'chat_id'):
                return msg.chat_id
    except (AttributeError, TypeError):
        pass
    return None


def safe_float_conversion(value: Any) -> Optional[float]:
    """Safely convert any value to float"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_string_operation(value: Any, operation: str, *args) -> Any:
    """Safely perform string operations with None checks"""
    if value is None:
        return None
    try:
        if hasattr(value, operation):
            method = getattr(value, operation)
            return method(*args)
    except (AttributeError, TypeError):
        pass
    return None


def ensure_list_compatibility(data: List[Any], target_type: type = dict) -> List[Dict[str, Any]]:
    """Ensure list items are compatible with expected type"""
    result = []
    for item in data:
        if isinstance(item, target_type):
            result.append(item)
        elif hasattr(item, '__dict__'):
            # Convert dataclass or object to dict
            if hasattr(item, '_asdict'):
                result.append(item._asdict())
            else:
                result.append(vars(item))
        else:
            # Skip incompatible items
            continue
    return result